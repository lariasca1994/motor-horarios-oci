from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


Rol = Literal["admin", "usuario"]


class UsuarioIn(BaseModel):
    """Alta de persona (registro público o por un admin): siempre con rol 'usuario'."""
    nombre: str = Field(min_length=1, max_length=100)
    email: EmailStr
    clave: str = Field(min_length=10, max_length=128)


class UsuarioCambios(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=100)
    rol: Optional[Rol] = None
    clave: Optional[str] = Field(default=None, min_length=10, max_length=128)
    activo: Optional[bool] = None


class Usuario(BaseModel):
    id: int
    nombre: str
    email: Optional[str] = None   # solo visible para admins y para uno mismo
    rol: Rol
    activo: bool = True


class Login(BaseModel):
    email: EmailStr
    clave: str = Field(min_length=1, max_length=128)


class Sesion(BaseModel):
    token: str
    usuario: Usuario


class CambioClave(BaseModel):
    actual: str = Field(min_length=1, max_length=128)
    nueva: str = Field(min_length=10, max_length=128)


class Reglas(BaseModel):
    no_antes_de: Optional[int] = Field(default=None, ge=0, le=23)
    no_despues_de: Optional[int] = Field(default=None, ge=1, le=24)
    dias_laborables: List[int] = Field(default=[0, 1, 2, 3, 4])

    @field_validator("dias_laborables")
    @classmethod
    def _dias_validos(cls, v: List[int]) -> List[int]:
        if not v or any(d < 0 or d > 6 for d in v):
            raise ValueError("dias_laborables debe contener valores entre 0 (lunes) y 6 (domingo)")
        return sorted(set(v))

    @model_validator(mode="after")
    def _rango(self):
        if (self.no_antes_de is not None and self.no_despues_de is not None
                and self.no_despues_de <= self.no_antes_de):
            raise ValueError("no_despues_de debe ser mayor que no_antes_de")
        return self


class DisponibilidadIn(BaseModel):
    inicio: datetime
    fin: datetime
    tipo: Literal["ocupado", "preferido"] = "ocupado"
    rrule: Optional[str] = Field(default=None, max_length=255)
    descripcion: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _rango(self):
        if self.fin <= self.inicio:
            raise ValueError("fin debe ser posterior a inicio")
        return self


class Disponibilidad(DisponibilidadIn):
    id: int
    usuario_id: int


class ReunionIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    duracion_min: int = Field(ge=15, le=480)
    ventana_inicio: datetime
    ventana_fin: datetime
    organizador_id: int
    participantes: List[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ventana(self):
        if self.ventana_fin <= self.ventana_inicio:
            raise ValueError("ventana_fin debe ser posterior a ventana_inicio")
        if (self.ventana_fin - self.ventana_inicio).days > 31:
            raise ValueError("la ventana no puede superar 31 días")
        return self


class Sugerencia(BaseModel):
    id: int
    inicio: datetime
    fin: datetime
    score: int


EstadoReunion = Literal["pendiente", "con_sugerencias", "sin_huecos", "confirmada", "cancelada"]


class Reunion(BaseModel):
    id: int
    titulo: str
    duracion_min: int
    ventana_inicio: datetime
    ventana_fin: datetime
    organizador_id: int
    estado: EstadoReunion
    inicio_confirmado: Optional[datetime] = None
    participantes: List[int] = Field(default_factory=list)
    sugerencias: List[Sugerencia] = Field(default_factory=list)


class Confirmacion(BaseModel):
    sugerencia_id: int
