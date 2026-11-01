"""
Model SQLAlchemy: PercobaanLogin
Menyimpan riwayat kegagalan dan status lockout login per akun dan per IP (Langkah 34).
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class PercobaanLogin(Base):
    """
    Tabel: percobaan_login
    Merekam akumulasi kegagalan login dan periode lockout berbasis akun (u:<username>)
    atau alamat IP (ip:<ip_address>) lintas worker uvicorn.
    """

    __tablename__ = "percobaan_login"

    id = Column(Integer, primary_key=True, index=True)
    kunci = Column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="Kunci pelacak unik: u:<username lower> atau ip:<ip>",
    )
    jumlah_gagal = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Akumulasi percobaan login gagal dalam jendela waktu",
    )
    jendela_mulai = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Waktu awal jendela perhitungan kegagalan",
    )
    terkunci_sampai = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Waktu hingga lockout berakhir; NULL jika tidak sedang terkunci",
    )
    diperbarui = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=func.now(),
        comment="Waktu pencatatan atau pembaruan terakhir",
    )

