"""
Admin audit logging service.
Tracks all admin actions performed on users and system entities.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, func
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.models.admin_audit_log import AdminAuditLog, AdminActionType
from app.models.user import User
from app.schemas.admin import AdminAuditLogSchema


class AdminAuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_action(
        self,
        admin_id: int,
        action_type: AdminActionType,
        target_user_id: Optional[int] = None,
        target_entity_type: Optional[str] = None,
        target_entity_id: Optional[int] = None,
        description: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> AdminAuditLog:
        """
        Log an admin action to the audit trail.
        
        Args:
            admin_id: ID of the admin performing the action
            action_type: Type of action performed
            target_user_id: ID of the user being affected (if applicable)
            target_entity_type: Type of entity being affected (e.g., "withdrawal_request")
            target_entity_id: ID of the entity being affected
            description: Human-readable description of the action
            old_values: Previous values (for changes)
            new_values: New values (for changes)
            context_data: Additional context
            
        Returns:
            AdminAuditLog: The created audit log entry
        """
        audit_log = AdminAuditLog(
            admin_id=admin_id,
            action_type=action_type,
            target_user_id=target_user_id,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            description=description,
            old_values=old_values,
            new_values=new_values,
            context_data=context_data,
        )
        self.db.add(audit_log)
        await self.db.commit()
        await self.db.refresh(audit_log)
        return audit_log

    async def get_user_audit_logs(
        self,
        target_user_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Get all audit logs affecting a specific user.
        """
        query = select(AdminAuditLog).where(
            AdminAuditLog.target_user_id == target_user_id
        ).order_by(desc(AdminAuditLog.created_at))
        
        total_query = select(AdminAuditLog).where(
            AdminAuditLog.target_user_id == target_user_id
        )
        total_result = await self.db.execute(select(func.count(AdminAuditLog.id)).where(
            AdminAuditLog.target_user_id == target_user_id
        ))
        total = total_result.scalar() or 0
        
        result = await self.db.execute(query.offset(skip).limit(limit))
        logs = result.scalars().all()
        
        # Convert to dict for response
        logs_data = []
        for log in logs:
            log_dict = {
                "id": log.id,
                "admin_id": log.admin_id,
                "action_type": log.action_type.value,
                "target_user_id": log.target_user_id,
                "target_entity_type": log.target_entity_type,
                "target_entity_id": log.target_entity_id,
                "description": log.description,
                "old_values": log.old_values,
                "new_values": log.new_values,
                "context_data": log.context_data,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            logs_data.append(log_dict)
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": logs_data,
        }

    async def get_admin_audit_logs(
        self,
        skip: int = 0,
        limit: int = 50,
        admin_id: Optional[int] = None,
        action_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get all audit logs (global view).
        Can filter by admin_id or action_type.
        """
        query = select(AdminAuditLog)
        
        if admin_id:
            query = query.where(AdminAuditLog.admin_id == admin_id)
        if action_type:
            try:
                action_enum = AdminActionType[action_type.upper()]
                query = query.where(AdminAuditLog.action_type == action_enum)
            except KeyError:
                pass
        
        query = query.order_by(desc(AdminAuditLog.created_at))
        
        # Count total
        count_query = select(AdminAuditLog)
        if admin_id:
            count_query = count_query.where(AdminAuditLog.admin_id == admin_id)
        if action_type:
            try:
                action_enum = AdminActionType[action_type.upper()]
                count_query = count_query.where(AdminAuditLog.action_type == action_enum)
            except KeyError:
                pass
        
        total_result = await self.db.execute(select(func.count(AdminAuditLog.id)).select_from(count_query.subquery()))
        total = total_result.scalar() or 0
        
        result = await self.db.execute(query.offset(skip).limit(limit))
        logs = result.scalars().all()
        
        # Convert to dict for response
        logs_data = []
        for log in logs:
            log_dict = {
                "id": log.id,
                "admin_id": log.admin_id,
                "action_type": log.action_type.value,
                "target_user_id": log.target_user_id,
                "target_entity_type": log.target_entity_type,
                "target_entity_id": log.target_entity_id,
                "description": log.description,
                "old_values": log.old_values,
                "new_values": log.new_values,
                "context_data": log.context_data,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            logs_data.append(log_dict)
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": logs_data,
        }
