from sqlalchemy import (
    Column, Integer, String, ForeignKey, DateTime, CheckConstraint, func
)
from sqlalchemy.orm import relationship
from database import Base


class TabelBarang(Base):
    __tablename__ = "tabel_barang"
    __table_args__ = (
        CheckConstraint("stok >= 0", name="ck_barang_stok_nonnegatif"),
    )

    id = Column(Integer, primary_key=True, index=True)
    nama = Column(String, index=True, nullable=False)
    stok = Column(Integer, nullable=False, default=0)
    # server_default dibutuhkan agar migrasi Alembic bisa mengisi baris lama
    lokasi_rak = Column(
        String, nullable=False,
        default="Belum diatur", server_default="Belum diatur",
    )

    transaksi = relationship("TabelTransaksi", back_populates="barang")


class TabelTransaksi(Base):
    __tablename__ = "tabel_transaksi"
    __table_args__ = (
        CheckConstraint("jumlah_diambil > 0", name="ck_transaksi_jumlah_positif"),
    )

    # ID Transaksi otomatis bertambah sendiri di database (1, 2, 3, dst.)
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    id_karyawan = Column(String, nullable=False)  # ID Karyawan / NIK / nama pengambil
    barang_id = Column(Integer, ForeignKey("tabel_barang.id"), nullable=False, index=True)
    jumlah_diambil = Column(Integer, nullable=False)
    keterangan = Column(String)
    # Waktu pencatatan, diisi otomatis oleh database (tidak perlu diubah di main.py)
    tanggal = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    barang = relationship("TabelBarang", back_populates="transaksi")


class TabelBarangMasuk(Base):
    """Catatan penambahan stok (barang masuk), sebagai jejak audit."""
    __tablename__ = "tabel_barang_masuk"
    __table_args__ = (
        CheckConstraint("jumlah > 0", name="ck_masuk_jumlah_positif"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    barang_id = Column(Integer, ForeignKey("tabel_barang.id"), nullable=False, index=True)
    jumlah = Column(Integer, nullable=False)
    keterangan = Column(String)                  # sumber barang, misalnya nama pemasok / no. PO
    oleh = Column(String, nullable=False)        # username yang mencatat (dari token)
    tanggal = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    barang = relationship("TabelBarang")