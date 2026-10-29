import os
import hmac
import datetime
from typing import Optional

import jwt  # pip install PyJWT  (BUKAN paket bernama "jwt")
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models, schemas, database

# Catatan: create_all hanya membuat tabel yang belum ada, TIDAK menambah kolom baru
# (misalnya lokasi_rak) ke tabel lama. Gunakan Alembic untuk perubahan struktur tabel.
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="ERP Modul Gudang")

# ==========================================
# CORS
# ==========================================
# Autentikasi memakai header Bearer (bukan cookie), jadi allow_credentials tidak diperlukan.
# Jika frontend dibuka langsung lewat file://, tambahkan "null" ke daftar ini.
ORIGINS_DIIZINKAN = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS_DIIZINKAN,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ==========================================
# KONFIGURASI JWT
# ==========================================
# Set lewat environment variable. Contoh (PowerShell):
#   $env:ERP_SECRET_KEY="isi-dengan-string-acak-panjang"
#   $env:ERP_ADMIN_PASSWORD="password-baru-anda"
# Nilai bawaan di bawah hanya untuk pengembangan lokal.
SECRET_KEY = os.getenv("ERP_SECRET_KEY", "dev-only-ganti-lewat-env")
ADMIN_USERNAME = os.getenv("ERP_ADMIN_USER", "manajer")
ADMIN_PASSWORD = os.getenv("ERP_ADMIN_PASSWORD", "gudang123")
ALGORITHM = "HS256"
MASA_BERLAKU_JAM = 2

if SECRET_KEY.startswith("dev-only"):
    print("PERINGATAN: ERP_SECRET_KEY belum diatur, memakai kunci pengembangan.")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==========================================
# LOGIN
# ==========================================
@app.post("/login")
def proses_login(form_data: OAuth2PasswordRequestForm = Depends()):
    # compare_digest membandingkan dalam waktu konstan (mencegah timing attack)
    user_ok = hmac.compare_digest(form_data.username.encode(), ADMIN_USERNAME.encode())
    pass_ok = hmac.compare_digest(form_data.password.encode(), ADMIN_PASSWORD.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Username atau password salah")

    kedaluwarsa = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=MASA_BERLAKU_JAM)
    isi_token = {"sub": form_data.username, "exp": kedaluwarsa}
    token = jwt.encode(isi_token, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}


# ==========================================
# VERIFIKASI TOKEN
# ==========================================
def verifikasi_admin(token_masuk: str = Depends(oauth2_scheme)) -> str:
    try:
        payload = jwt.decode(token_masuk, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Waktu token habis, silakan login ulang!")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token palsu atau rusak!")

    username = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Token tidak valid")
    return username


# ==========================================
# BARANG
# ==========================================
def barang_ke_dict(b: models.TabelBarang) -> dict:
    return {"id": b.id, "nama": b.nama, "stok": b.stok, "lokasi_rak": b.lokasi_rak}


@app.get("/barang")
def get_semua_barang(db: Session = Depends(get_db), _user: str = Depends(verifikasi_admin)):
    daftar = db.query(models.TabelBarang).order_by(models.TabelBarang.id).all()
    return {"data": [barang_ke_dict(b) for b in daftar]}


@app.post("/barang")
def tambah_barang(
    barang: schemas.BarangMasuk,
    db: Session = Depends(get_db),
    _user: str = Depends(verifikasi_admin),
):
    if barang.stok < 0:
        raise HTTPException(status_code=400, detail="Stok awal tidak boleh negatif")

    if db.query(models.TabelBarang).filter(models.TabelBarang.id == barang.id).first():
        raise HTTPException(status_code=400, detail=f"ID barang {barang.id} sudah dipakai")

    barang_baru = models.TabelBarang(
        id=barang.id,
        nama=barang.nama,
        stok=barang.stok,
        lokasi_rak=barang.lokasi_rak,
    )
    db.add(barang_baru)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Data barang tidak valid atau ID sudah dipakai")

    return {"pesan": f"Barang '{barang.nama}' berhasil disimpan"}


@app.delete("/barang/{barang_id}")
def hapus_barang(
    barang_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(verifikasi_admin),
):
    barang = db.query(models.TabelBarang).filter(models.TabelBarang.id == barang_id).first()
    if not barang:
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan")

    # Jaga riwayat transaksi tetap utuh: barang yang sudah pernah diambil tidak boleh dihapus.
    # (Hapus blok ini jika Anda memang ingin mengizinkannya.)
    ada_transaksi = (
        db.query(models.TabelTransaksi)
        .filter(models.TabelTransaksi.barang_id == barang_id)
        .first()
    )
    ada_stok_masuk = (
        db.query(models.TabelBarangMasuk)
        .filter(models.TabelBarangMasuk.barang_id == barang_id)
        .first()
    )
    if ada_transaksi or ada_stok_masuk:
        raise HTTPException(
            status_code=409,
            detail="Barang tidak bisa dihapus karena sudah memiliki riwayat transaksi atau penambahan stok",
        )

    db.delete(barang)
    db.commit()
    return {"pesan": "Barang berhasil dihapus"}


# ==========================================
# BARANG MASUK (TAMBAH STOK)
# ==========================================
@app.post("/barang/{barang_id}/stok-masuk")
def tambah_stok(
    barang_id: int,
    data: schemas.StokMasuk,
    db: Session = Depends(get_db),
    user: str = Depends(verifikasi_admin),
):
    barang = db.query(models.TabelBarang).filter(models.TabelBarang.id == barang_id).first()
    if not barang:
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan")

    barang.stok += data.jumlah
    db.add(models.TabelBarangMasuk(
        barang_id=barang_id,
        jumlah=data.jumlah,
        keterangan=data.keterangan,
        oleh=user,
    ))

    # Penambahan stok dan catatannya disimpan dalam satu commit (atomik)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Gagal menambah stok, stok tidak berubah")

    db.refresh(barang)
    return {
        "pesan": f"Stok '{barang.nama}' bertambah {data.jumlah} unit",
        "sisa_stok": barang.stok,
    }


# ==========================================
# TRANSAKSI PENGAMBILAN
# ==========================================
@app.post("/transaksi")
def catat_transaksi(
    trx: schemas.TransaksiCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(verifikasi_admin),
):
    if trx.jumlah_diambil <= 0:
        raise HTTPException(status_code=400, detail="Jumlah diambil harus lebih dari 0")

    barang = db.query(models.TabelBarang).filter(models.TabelBarang.id == trx.barang_id).first()
    if not barang:
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan")
    if barang.stok < trx.jumlah_diambil:
        raise HTTPException(
            status_code=400,
            detail=f"Stok tidak mencukupi (tersisa {barang.stok})",
        )

    barang.stok -= trx.jumlah_diambil

    transaksi_baru = models.TabelTransaksi(
        id_karyawan=trx.id_karyawan,
        barang_id=trx.barang_id,
        jumlah_diambil=trx.jumlah_diambil,
        keterangan=trx.keterangan,
    )
    db.add(transaksi_baru)

    # Pengurangan stok dan pencatatan transaksi disimpan dalam satu commit (atomik)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Transaksi gagal disimpan, stok tidak berubah")

    db.refresh(transaksi_baru)
    db.refresh(barang)
    return {
        "pesan": f"Transaksi berhasil dicatat dengan No. TRX-{transaksi_baru.id}",
        "sisa_stok": barang.stok,
    }


# ==========================================
# RIWAYAT TRANSAKSI
# ==========================================
def tanggal_ke_iso(t):
    """SQLite menyimpan waktu UTC tanpa zona; tandai sebagai UTC agar browser
    bisa mengonversinya ke zona waktu lokal pengguna."""
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.isoformat()


@app.get("/transaksi")
def get_riwayat_transaksi(
    limit: int = Query(100, ge=1, le=500),
    barang_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _user: str = Depends(verifikasi_admin),
):
    q = db.query(models.TabelTransaksi, models.TabelBarang.nama).outerjoin(
        models.TabelBarang, models.TabelBarang.id == models.TabelTransaksi.barang_id
    )
    if barang_id is not None:
        q = q.filter(models.TabelTransaksi.barang_id == barang_id)

    baris = q.order_by(models.TabelTransaksi.id.desc()).limit(limit).all()
    return {
        "data": [
            {
                "id": t.id,
                "kode": f"TRX-{t.id}",
                "id_karyawan": t.id_karyawan,
                "barang_id": t.barang_id,
                "nama_barang": nama,
                "jumlah_diambil": t.jumlah_diambil,
                "keterangan": t.keterangan,
                "tanggal": tanggal_ke_iso(t.tanggal),
            }
            for t, nama in baris
        ]
    }


# ==========================================
# EDIT BARANG
# ==========================================
# Stok sengaja tidak bisa diubah di sini; ubah stok lewat Barang masuk / Pengambilan
# supaya setiap perubahan angka punya catatan.
@app.put("/barang/{barang_id}")
def ubah_barang(
    barang_id: int,
    data: schemas.BarangUbah,
    db: Session = Depends(get_db),
    _user: str = Depends(verifikasi_admin),
):
    barang = db.query(models.TabelBarang).filter(models.TabelBarang.id == barang_id).first()
    if not barang:
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan")

    barang.nama = data.nama
    barang.lokasi_rak = data.lokasi_rak
    db.commit()
    return {"pesan": f"Barang '{barang.nama}' berhasil diperbarui"}


# ==========================================
# MUTASI STOK (barang masuk + pengambilan, digabung)
# ==========================================
@app.get("/mutasi")
def get_mutasi_stok(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: str = Depends(verifikasi_admin),
):
    keluar = (
        db.query(models.TabelTransaksi, models.TabelBarang.nama)
        .outerjoin(models.TabelBarang, models.TabelBarang.id == models.TabelTransaksi.barang_id)
        .order_by(models.TabelTransaksi.id.desc()).limit(limit).all()
    )
    masuk = (
        db.query(models.TabelBarangMasuk, models.TabelBarang.nama)
        .outerjoin(models.TabelBarang, models.TabelBarang.id == models.TabelBarangMasuk.barang_id)
        .order_by(models.TabelBarangMasuk.id.desc()).limit(limit).all()
    )

    data = []
    for t, nama in keluar:
        data.append({
            "tipe": "keluar", "kode": f"TRX-{t.id}", "id": t.id,
            "barang_id": t.barang_id, "nama_barang": nama,
            "jumlah": t.jumlah_diambil, "oleh": t.id_karyawan,
            "keterangan": t.keterangan, "tanggal": tanggal_ke_iso(t.tanggal),
        })
    for m, nama in masuk:
        data.append({
            "tipe": "masuk", "kode": f"MSK-{m.id}", "id": m.id,
            "barang_id": m.barang_id, "nama_barang": nama,
            "jumlah": m.jumlah, "oleh": m.oleh,
            "keterangan": m.keterangan, "tanggal": tanggal_ke_iso(m.tanggal),
        })

    data.sort(key=lambda x: (x["tanggal"] or "", x["id"]), reverse=True)
    return {"data": data[:limit]}