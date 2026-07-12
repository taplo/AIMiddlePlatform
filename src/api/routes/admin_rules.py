import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func

from src.core.database import Rule, RuleBinding

logger = logging.getLogger(__name__)

rules_router = APIRouter(prefix="/api/v1/admin/rules", tags=["admin", "rules"])
bindings_router = APIRouter(prefix="/api/v1/admin/rule-bindings", tags=["admin", "rule-bindings"])

_db_session_factory = None


def init_db_session_factory(factory) -> None:
    global _db_session_factory
    _db_session_factory = factory


class RuleCreate(BaseModel):
    name: str
    rule_type: str
    config: str
    severity: str = "medium"
    enabled: bool = True
    description: str = ""


class RuleUpdate(BaseModel):
    name: str | None = None
    rule_type: str | None = None
    config: str | None = None
    severity: str | None = None
    enabled: bool | None = None
    description: str | None = None


class RuleBindingCreate(BaseModel):
    rule_id: int
    camera_id: str | None = None
    scene_type: str | None = None
    config_overrides: str | None = None
    enabled: bool = True
    priority: int = 0


class RuleBindingUpdate(BaseModel):
    camera_id: str | None = None
    scene_type: str | None = None
    config_overrides: str | None = None
    enabled: bool | None = None
    priority: int | None = None


def _rule_to_dict(rule: Rule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "config": rule.config,
        "severity": rule.severity,
        "enabled": rule.enabled,
        "description": rule.description,
        "created_at": str(rule.created_at) if rule.created_at else None,
        "updated_at": str(rule.updated_at) if rule.updated_at else None,
    }


def _binding_to_dict(binding: RuleBinding) -> dict:
    return {
        "id": binding.id,
        "rule_id": binding.rule_id,
        "camera_id": binding.camera_id,
        "scene_type": binding.scene_type,
        "config_overrides": binding.config_overrides,
        "enabled": binding.enabled,
        "priority": binding.priority,
        "created_at": str(binding.created_at) if binding.created_at else None,
        "updated_at": str(binding.updated_at) if binding.updated_at else None,
    }


# ---- Rule endpoints ----


@rules_router.post("")
async def create_rule(body: RuleCreate) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        existing = (await session.execute(select(Rule).where(Rule.name == body.name))).scalar_one_or_none()
        if existing:
            raise HTTPException(409, f"Rule with name '{body.name}' already exists")
        rule = Rule(
            name=body.name,
            rule_type=body.rule_type,
            config=body.config,
            severity=body.severity,
            enabled=body.enabled,
            description=body.description,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
    return _rule_to_dict(rule)


@rules_router.put("/{rule_id}")
async def update_rule(rule_id: int, body: RuleUpdate) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        rule = await session.get(Rule, rule_id)
        if rule is None:
            raise HTTPException(404, f"Rule {rule_id} not found")
        if body.name is not None:
            rule.name = body.name
        if body.rule_type is not None:
            rule.rule_type = body.rule_type
        if body.config is not None:
            rule.config = body.config
        if body.severity is not None:
            rule.severity = body.severity
        if body.enabled is not None:
            rule.enabled = body.enabled
        if body.description is not None:
            rule.description = body.description
        await session.commit()
        await session.refresh(rule)
    return _rule_to_dict(rule)


@rules_router.delete("/{rule_id}")
async def delete_rule(rule_id: int) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        rule = await session.get(Rule, rule_id)
        if rule is None:
            raise HTTPException(404, f"Rule {rule_id} not found")
        rule.enabled = False
        await session.commit()
    return {"status": "deleted", "id": rule_id}


@rules_router.get("")
async def list_rules(
    rule_type: str | None = Query(None),
    enabled: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        query = select(Rule).order_by(Rule.created_at.desc())
        count_query = select(sa_func.count()).select_from(Rule)
        if rule_type is not None:
            query = query.where(Rule.rule_type == rule_type)
            count_query = count_query.where(Rule.rule_type == rule_type)
        if enabled is not None:
            query = query.where(Rule.enabled == enabled)
            count_query = count_query.where(Rule.enabled == enabled)

        total = (await session.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        rows = (await session.execute(query.offset(offset).limit(page_size))).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_rule_to_dict(r) for r in rows],
    }


@rules_router.get("/{rule_id}")
async def get_rule(rule_id: int) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        rule = await session.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(404, f"Rule {rule_id} not found")
    return _rule_to_dict(rule)


# ---- RuleBinding endpoints ----


@bindings_router.post("")
async def create_binding(body: RuleBindingCreate) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        rule = await session.get(Rule, body.rule_id)
        if rule is None:
            raise HTTPException(404, f"Rule {body.rule_id} not found")
        dup = (await session.execute(
            select(RuleBinding).where(
                RuleBinding.rule_id == body.rule_id,
                RuleBinding.camera_id == body.camera_id,
            )
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(409, "Binding already exists for this rule_id and camera_id")
        binding = RuleBinding(
            rule_id=body.rule_id,
            camera_id=body.camera_id,
            scene_type=body.scene_type,
            config_overrides=body.config_overrides,
            enabled=body.enabled,
            priority=body.priority,
        )
        session.add(binding)
        await session.commit()
        await session.refresh(binding)
    return _binding_to_dict(binding)


@bindings_router.put("/{binding_id}")
async def update_binding(binding_id: int, body: RuleBindingUpdate) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        binding = await session.get(RuleBinding, binding_id)
        if binding is None:
            raise HTTPException(404, f"RuleBinding {binding_id} not found")
        if body.camera_id is not None:
            binding.camera_id = body.camera_id
        if body.scene_type is not None:
            binding.scene_type = body.scene_type
        if body.config_overrides is not None:
            binding.config_overrides = body.config_overrides
        if body.enabled is not None:
            binding.enabled = body.enabled
        if body.priority is not None:
            binding.priority = body.priority
        await session.commit()
        await session.refresh(binding)
    return _binding_to_dict(binding)


@bindings_router.delete("/{binding_id}")
async def delete_binding(binding_id: int) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        binding = await session.get(RuleBinding, binding_id)
        if binding is None:
            raise HTTPException(404, f"RuleBinding {binding_id} not found")
        binding.enabled = False
        await session.commit()
    return {"status": "deleted", "id": binding_id}


@bindings_router.get("")
async def list_bindings(
    rule_id: int | None = Query(None),
    camera_id: str | None = Query(None),
    scene_type: str | None = Query(None),
    enabled: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        query = select(RuleBinding).order_by(RuleBinding.priority.desc(), RuleBinding.created_at.desc())
        count_query = select(sa_func.count()).select_from(RuleBinding)
        if rule_id is not None:
            query = query.where(RuleBinding.rule_id == rule_id)
            count_query = count_query.where(RuleBinding.rule_id == rule_id)
        if camera_id is not None:
            query = query.where(RuleBinding.camera_id == camera_id)
            count_query = count_query.where(RuleBinding.camera_id == camera_id)
        if scene_type is not None:
            query = query.where(RuleBinding.scene_type == scene_type)
            count_query = count_query.where(RuleBinding.scene_type == scene_type)
        if enabled is not None:
            query = query.where(RuleBinding.enabled == enabled)
            count_query = count_query.where(RuleBinding.enabled == enabled)

        total = (await session.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        rows = (await session.execute(query.offset(offset).limit(page_size))).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_binding_to_dict(b) for b in rows],
    }


@bindings_router.get("/{binding_id}")
async def get_binding(binding_id: int) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        binding = await session.get(RuleBinding, binding_id)
    if binding is None:
        raise HTTPException(404, f"RuleBinding {binding_id} not found")
    return _binding_to_dict(binding)
