from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints

# Teks: spasi di awal/akhir dibuang, tidak boleh kosong, dan dibatasi panjangnya
TeksPendek = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
TeksKeterangan = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class BarangMasuk(BaseModel):
    id: int = Field(ge=1)               # ID barang minimal 1
    nama: TeksPendek
    stok: int = Field(ge=0)             # stok awal tidak boleh negatif
    lokasi_rak: TeksPendek = "Belum diatur"


class TransaksiCreate(BaseModel):
    id_karyawan: TeksPendek             # ID Karyawan / Nama Pengambil
    barang_id: int = Field(ge=1)
    jumlah_diambil: int = Field(ge=1)   # minimal 1 unit
    keterangan: TeksKeterangan


class StokMasuk(BaseModel):
    jumlah: int = Field(ge=1, le=1_000_000)
    keterangan: Optional[TeksKeterangan] = None


class BarangUbah(BaseModel):
    nama: TeksPendek
    lokasi_rak: TeksPendek