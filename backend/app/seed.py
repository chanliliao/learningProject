import json
from pathlib import Path
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.schema import TargetSchema

_SCHEMAS_DIR = Path(__file__).parent / "schemas"

_SEED_DATA = [
    ("distributor_a", "1.0", "target_distributor_a.json"),
    ("distributor_b", "1.0", "target_distributor_b.json"),
]


async def seed_target_schemas(session: AsyncSession) -> None:
    for name, version, filename in _SEED_DATA:
        existing = (
            await session.exec(
                select(TargetSchema).where(
                    TargetSchema.name == name,
                    TargetSchema.version == version,
                )
            )
        ).first()
        if existing:
            continue
        definition = json.loads((_SCHEMAS_DIR / filename).read_text())
        session.add(TargetSchema(name=name, version=version, definition=definition))
