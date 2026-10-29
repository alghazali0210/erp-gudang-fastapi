import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Folder proyek = satu tingkat di atas folder alembic/. Tidak bergantung pada
# folder tempat perintah `alembic` dijalankan.
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import database  # noqa: E402
import models    # noqa: E402  (wajib diimpor agar tabel terdaftar di metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Satu sumber kebenaran: URL database diambil dari database.py, sehingga Alembic
# selalu memakai file yang sama dengan aplikasi (sql_app.db).
# Tanda % digandakan karena configparser memperlakukannya sebagai karakter khusus.
config.set_main_option(
    "sqlalchemy.url", database.SQLALCHEMY_DATABASE_URL.replace("%", "%%")
)

target_metadata = models.Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,   # SQLite tidak bisa ALTER kolom langsung
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,   # SQLite tidak bisa ALTER kolom langsung
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()