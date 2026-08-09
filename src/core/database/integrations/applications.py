from ..sLilyDatabaseAccess import LilyDatabaseAccess

from typing import Dict

from typing import Dict, List, Optional, Any


class ApplicationManagement:
    def __init__(self, db: LilyDatabaseAccess):
        super().__init__()

        self.db: LilyDatabaseAccess = db

    async def create_application(
        self,
        guild_id: int,
        application_name: str,
        application_description: str,
        submission_forum_id: int,
        submit_btn_label: str
    ) -> Dict[str, Any]:
        application_id = await self.db.execute(
            """
            INSERT INTO application (guild_id, name, description, active, current_wave, submission_forum_id, submit_btn_label)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, application_name, application_description, 1, 0, submission_forum_id, submit_btn_label)
        )

        return {
            "id": application_id,
            "guild_id": guild_id,
            "name": application_name,
            "description": application_description,
            "active": 1,
            "current_wave": 0
        }

    async def get_application(self, guild_id: int, application_id: int) -> Optional[Dict[str, Any]]:
        row = await self.db.fetch_one(
            "SELECT * FROM application WHERE id = ? AND guild_id = ?",
            (application_id, guild_id)
        )

        if row is None:
            return None

        return dict(row)

    async def get_pending_application(self, guild_id: int):
        ...
    
    async def get_application_with_view(
        self,
        guild_id: int,
        application_id: int
    ) -> Optional[Dict[str, Any]]:
        row = await self.db.fetch_one(
            """
            SELECT
                a.*,
                av.channel_id,
                av.message_id
            FROM application AS a
            LEFT JOIN application_views AS av
                ON av.application_id = a.id
            AND av.guild_id = a.guild_id
            WHERE a.guild_id = ?
            AND a.id = ?
            """,
            (guild_id, application_id)
        )

        if row is None:
            return None
        
        return dict(row)

    async def get_applications_by_guild(
        self,
        guild_id: int,
        active_only: bool = False
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM application WHERE guild_id = ?"
        params: tuple = (guild_id,)

        if active_only:
            query += " AND active = 1"

        rows = await self.db.fetch_all(query, params)

        return [dict(row) for row in rows]

    async def update_application(
        self,
        guild_id: int,
        application_id: int,
        application_name: Optional[str] = None,
        application_description: Optional[str] = None,
        submit_btn_label: Optional[str] = None
    ) -> bool:
        fields: List[str] = []
        params: List[Any] = []

        if application_name is not None:
            fields.append("name = ?")
            params.append(application_name)

        if application_description is not None:
            fields.append("description = ?")
            params.append(application_description)

        if submit_btn_label is not None:
            fields.append("submit_btn_label = ?")
            params.append(submit_btn_label)

        if not fields:
            return False

        params.append(application_id)
        params.append(guild_id)

        rows_affected = await self.db.execute(
            f"UPDATE application SET {', '.join(fields)} WHERE id = ? AND guild_id = ?",
            tuple(params),
            row_count=True
        )

        return bool(rows_affected)

    async def set_active(
        self,
        guild_id: int,
        application_id: int,
        active: bool
    ) -> Dict[str, Any]:
        application = await self.db.fetch_one(
            """
            SELECT active
            FROM application
            WHERE id = ? AND guild_id = ?
            """,
            (application_id, guild_id)
        )

        if application is None:
            return {
                "success": False,
                "message": "Application not found."
            }

        if bool(application["active"]) == active:
            status = "active" if active else "inactive"
            return {
                "success": False,
                "message": f"Application is already {status}."
            }

        await self.db.execute(
            """
            UPDATE application
            SET active = ?
            WHERE id = ? AND guild_id = ?
            """,
            (int(active), application_id, guild_id)
        )

        status = "activated" if active else "deactivated"

        return {
            "success": True,
            "message": f"Application {status} successfully.",
            "status": status
        }

    async def advance_wave(self, guild_id: int, application_id: int) -> Optional[int]:
        application = await self.get_application(guild_id, application_id)

        if application is None:
            return None

        new_wave = application["current_wave"] + 1

        await self.db.execute(
            "UPDATE application SET current_wave = ? WHERE id = ? AND guild_id = ?",
            (new_wave, application_id, guild_id)
        )

        return new_wave

    async def delete_application(self, guild_id: int, application_id: int) -> bool:
        rows_affected = await self.db.execute(
            "DELETE FROM application WHERE id = ? AND guild_id = ?",
            (application_id, guild_id),
            row_count=True
        )

        return bool(rows_affected)

    async def create_question(
        self,
        guild_id: int,
        label: str,
        type: str,
        description: Optional[str] = None,
        placeholder: Optional[str] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        metadata: Optional[str] = None
    ) -> Dict[str, Any]:
        question_id = await self.db.execute(
            """
            INSERT INTO application_questions
                (guild_id, label, description, placeholder, min_length, max_length, "type", metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                label,
                description,
                placeholder,
                min_length,
                max_length,
                type,
                metadata
            )
        )

        return {
            "id": question_id,
            "guild_id": guild_id,
            "label": label,
            "description": description,
            "placeholder": placeholder,
            "min_length": min_length,
            "max_length": max_length,
            "type": type,
            "metadata": metadata
        }

    async def get_question(self, guild_id: int, question_id: int) -> Optional[Dict[str, Any]]:
        row = await self.db.fetch_one(
            "SELECT * FROM application_questions WHERE id = ? AND guild_id = ?",
            (question_id, guild_id)
        )

        if row is None:
            return None

        return dict(row)

    async def get_questions_by_guild(self, guild_id: int) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            "SELECT * FROM application_questions WHERE guild_id = ?",
            (guild_id,)
        )

        return [dict(row) for row in rows]

    async def update_question(
        self,
        guild_id: int,
        question_id: int,
        label: Optional[str] = None,
        description: Optional[str] = None,
        placeholder: Optional[str] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        type: Optional[str] = None,
        metadata: Optional[str] = None
    ) -> bool:
        fields: List[str] = []
        params: List[Any] = []

        if label is not None:
            fields.append("label = ?")
            params.append(label)

        if description is not None:
            fields.append("description = ?")
            params.append(description)

        if placeholder is not None:
            fields.append("placeholder = ?")
            params.append(placeholder)

        if min_length is not None:
            fields.append("min_length = ?")
            params.append(min_length)

        if max_length is not None:
            fields.append("max_length = ?")
            params.append(max_length)

        if type is not None:
            fields.append("\"type\" = ?")
            params.append(type)

        if metadata is not None:
            fields.append("metadata = ?")
            params.append(metadata)

        if not fields:
            return False

        params.append(question_id)
        params.append(guild_id)

        rows_affected = await self.db.execute(
            f"UPDATE application_questions SET {', '.join(fields)} WHERE id = ? AND guild_id = ?",
            tuple(params),
            row_count=True
        )

        return bool(rows_affected)

    async def delete_question(self, guild_id: int, question_id: int) -> bool:
        rows_affected = await self.db.execute(
            "DELETE FROM application_questions WHERE id = ? AND guild_id = ?",
            (question_id, guild_id),
            row_count=True
        )

        return bool(rows_affected)

    async def create_group(
        self,
        guild_id: int,
        name: str,
        description: str,
        question_ids: List[int | None]
    ) -> Dict[str, Any]:
        async with self.db.transaction() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO application_groups (guild_id, name, description)
                VALUES (?, ?, ?)
                """,
                (guild_id, name, description)
            )
            group_id = cursor.get_cursor().lastrowid

            if question_ids:
                await conn.executemany(
                    """
                    INSERT INTO application_group_questions (guild_id, group_id, question_id, position)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (guild_id, group_id, question_id, position)
                        for position, question_id in enumerate(question_ids) if question_id is not None
                    ]
                )

        return {
            "id": group_id,
            "guild_id": guild_id,
            "name": name,
            "description": description,
            "question_ids": question_ids
        }

    async def get_group(self, guild_id: int, group_id: int) -> Optional[Dict[str, Any]]:
        row = await self.db.fetch_one(
            "SELECT * FROM application_groups WHERE id = ? AND guild_id = ?",
            (group_id, guild_id)
        )

        if row is None:
            return None

        group = dict(row)
        group["questions"] = await self.get_group_questions(guild_id, group_id)

        return group

    async def get_group_questions(self, guild_id: int, group_id: int) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            """
            SELECT q.*, gq.position
            FROM application_group_questions gq
            JOIN application_questions q ON q.id = gq.question_id
            WHERE gq.group_id = ? AND gq.guild_id = ?
            ORDER BY gq.position
            """,
            (group_id, guild_id)
        )

        return [dict(row) for row in rows]

    async def get_groups_by_guild(self, guild_id: int) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            "SELECT * FROM application_groups WHERE guild_id = ?",
            (guild_id,)
        )

        return [dict(row) for row in rows]

    async def update_group(
        self,
        guild_id: int,
        group_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> bool:
        fields: List[str] = []
        params: List[Any] = []

        if name is not None:
            fields.append("name = ?")
            params.append(name)

        if description is not None:
            fields.append("description = ?")
            params.append(description)

        if not fields:
            return False

        params.append(group_id)
        params.append(guild_id)

        rows_affected = await self.db.execute(
            f"UPDATE application_groups SET {', '.join(fields)} WHERE id = ? AND guild_id = ?",
            tuple(params),
            row_count=True
        )

        return bool(rows_affected)

    async def set_group_questions(
        self,
        guild_id: int,
        group_id: int,
        question_ids: List[int]
    ) -> bool:
        group = await self.get_group(guild_id, group_id)

        if group is None:
            return False

        await self.db.execute(
            "DELETE FROM application_group_questions WHERE group_id = ? AND guild_id = ?",
            (group_id, guild_id)
        )

        if question_ids:
            await self.db.executemany(
                """
                INSERT INTO application_group_questions (guild_id, group_id, question_id, position)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (guild_id, group_id, question_id, position)
                    for position, question_id in enumerate(question_ids)
                ]
            )

        return True

    async def delete_group(self, guild_id: int, group_id: int) -> bool:
        await self.db.execute(
            "DELETE FROM application_group_questions WHERE group_id = ? AND guild_id = ?",
            (group_id, guild_id)
        )

        rows_affected = await self.db.execute(
            "DELETE FROM application_groups WHERE id = ? AND guild_id = ?",
            (group_id, guild_id),
            row_count=True
        )

        return bool(rows_affected)
    
    async def assign_groups(
        self,
        guild_id: int,
        application_id: int,
        group_ids: List[int]
    ) -> None:
        async with self.db.transaction() as conn:
            for position, group_id in enumerate(group_ids):
                await conn.execute(
                    """
                    INSERT INTO application_group_assignments (guild_id, application_id, group_id, position)
                    VALUES (?, ?, ?, ?)
                    """,
                    (guild_id, application_id, group_id, position)
                )

    async def get_application_groups(
        self,
        guild_id: int,
        application_id: int
    ) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            """
            SELECT g.*, aga.position
            FROM application_group_assignments aga
            JOIN application_groups g ON g.id = aga.group_id
            WHERE aga.application_id = ? AND aga.guild_id = ?
            ORDER BY aga.position
            """,
            (application_id, guild_id)
        )

        return [dict(row) for row in rows]

    async def get_group_applications(
        self,
        guild_id: int,
        group_id: int
    ) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            """
            SELECT a.*
            FROM application_group_assignments aga
            JOIN application a ON a.id = aga.application_id
            WHERE aga.group_id = ? AND aga.guild_id = ?
            """,
            (group_id, guild_id)
        )

        return [dict(row) for row in rows]

    async def set_application_groups(
        self,
        guild_id: int,
        application_id: int,
        group_ids: List[int]
    ) -> None:
        async with self.db.transaction() as conn:
            await conn.execute(
                "DELETE FROM application_group_assignments WHERE application_id = ? AND guild_id = ?",
                (application_id, guild_id)
            )

            for position, group_id in enumerate(group_ids):
                await conn.execute(
                    """
                    INSERT INTO application_group_assignments (guild_id, application_id, group_id, position)
                    VALUES (?, ?, ?, ?)
                    """,
                    (guild_id, application_id, group_id, position)
                )

    async def remove_group_assignment(
        self,
        guild_id: int,
        application_id: int,
        group_id: int
    ) -> bool:
        rows_affected = await self.db.execute(
            "DELETE FROM application_group_assignments WHERE application_id = ? AND group_id = ? AND guild_id = ?",
            (application_id, group_id, guild_id),
            row_count=True
        )

        return bool(rows_affected)

    async def create_application_view(
        self,
        guild_id: int,
        channel_id: int,
        application_id: int,
        message_id: int,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO application_views (
                guild_id,
                channel_id,
                application_id,
                message_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, channel_id, application_id, message_id),
        )
    
    async def get_application_questions(
        self,
        guild_id: int,
        application_id: int,
    ) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            """
            SELECT
                q.*,
                ag.id AS group_id,
                ag.name AS group_name,
                ag.description AS group_description,
                aga.position AS group_position,
                agq.position AS question_position
            FROM application_group_assignments AS aga
            JOIN application_groups AS ag
                ON ag.id = aga.group_id
            AND ag.guild_id = aga.guild_id
            JOIN application_group_questions AS agq
                ON agq.group_id = ag.id
            AND agq.guild_id = ag.guild_id
            JOIN application_questions AS q
                ON q.id = agq.question_id
            AND q.guild_id = agq.guild_id
            WHERE aga.guild_id = ?
            AND aga.application_id = ?
            ORDER BY
                aga.position,
                agq.position
            """,
            (guild_id, application_id),
        )

        return [dict(row) for row in rows]
    
    async def get_unanswered_application_question(
        self,
        submission_id: int,
    ) -> Optional[Dict[str, Any]]:
        row = await self.db.fetch_one(
            """
            SELECT
                q.*,
                aga.group_id,
                aga.position AS group_position,
                agq.position AS question_position,
                s.id AS submission_id,
                s.guild_id,
                s.application_id,
                s.member_id,
                s.wave,
                s.status
            FROM application_submissions s
            JOIN application_group_assignments aga
                ON aga.application_id = s.application_id
            AND aga.guild_id = s.guild_id
            JOIN application_group_questions agq
                ON agq.group_id = aga.group_id
            AND agq.guild_id = aga.guild_id
            JOIN application_questions q
                ON q.id = agq.question_id
            AND q.guild_id = agq.guild_id
            LEFT JOIN application_submission_answers a
                ON a.submission_id = s.id
            AND a.question_id = q.id
            WHERE s.id = ?
            AND a.id IS NULL
            ORDER BY
                aga.position,
                agq.position
            LIMIT 1
            """,
            (submission_id,)
        )

        return dict(row) if row else None

    async def ensure_member(self, member_id: int, guild_id: int) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO members (member_id, guild_id) VALUES (?, ?)",
            (member_id, guild_id),
        )

    async def save_application_answer(
        self,
        submission_id: int,
        group_id: int,
        question_id: int,
        answer_value: str,
    ) -> bool:
        rows_affected = await self.db.execute(
            """
            INSERT INTO application_submission_answers (
                submission_id,
                group_id,
                question_id,
                answer_value
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(submission_id, question_id)
            DO UPDATE SET
                answer_value = excluded.answer_value,
                group_id = excluded.group_id
            """,
            (
                submission_id,
                group_id,
                question_id,
                answer_value,
            ),
            row_count=True,
        )

        return bool(rows_affected)
    
    async def create_application_submission(
        self,
        guild_id: int,
        application_id: int,
        member_id: int,
        wave: int,
    ) -> Dict[str, Any]:

        await self.ensure_member(member_id, guild_id)

        submission_id = await self.db.execute(
            """
            INSERT INTO application_submissions (
                guild_id,
                application_id,
                member_id,
                wave,
                status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                application_id,
                member_id,
                wave,
                "in_progress",
            ),
        )

        return {
            "id": submission_id,
            "guild_id": guild_id,
            "application_id": application_id,
            "member_id": member_id,
            "wave": wave,
            "status": "in_progress",
        }

    async def get_submission(
        self,
        guild_id: int,
        application_id: int,
        member_id: int,
        wave: int
    ) -> Optional[Dict[str, Any]]:
        row = await self.db.fetch_one(
            """
            SELECT *
            FROM application_submissions
            WHERE guild_id = ?
            AND application_id = ?
            AND member_id = ?
            AND wave = ?
            """,
            (guild_id, application_id, member_id, wave),
        )

        return dict(row) if row else None

    async def delete_submission(
        self,
        guild_id: int,
        submission_id: int,
        member_id: int,
        wave: int,
    ) -> bool:
        row_count = await self.db.execute(
            """
            DELETE FROM application_submissions
            WHERE guild_id = ?
            AND id = ?
            AND member_id = ?
            AND wave = ?
            """,
            (
                guild_id,
                submission_id,
                member_id,
                wave,
            ),
            row_count=True,
        )

        return row_count is not None and row_count > 0
    
    async def get_pending_submission(
        self,
        member_id: int,
    ) -> Optional[Dict[str, Any]]:
        
        row = await self.db.fetch_one(
            """
            SELECT *
            FROM application_submissions
            WHERE member_id = ?
            AND status = 'in_progress'
            ORDER BY id DESC
            LIMIT 1
            """,
            (member_id,),
        )

        return dict(row) if row else None

    async def get_pending_submissions(
        self,
        guild_id: int,
        application_id: Optional[int] = None
    ) -> Optional[List[Dict[str, Any]]]:

        query = """
            SELECT
                s.id AS submission_id,
                s.guild_id,
                s.application_id,
                s.member_id,
                s.wave,
                s.status,
                s.verification_status,
                s.submitted_at,
                s.submission_thread_reference,
                a.name AS application_name,
                a.description AS application_description,
                a.submit_btn_label,
                a.active AS application_active,
                a.current_wave AS application_current_wave,
                a.submission_forum_id
            FROM application_submissions s
            JOIN application a ON a.id = s.application_id
            WHERE s.guild_id = ?
            AND s.status = 'in_progress'
        """

        params: List[Any] = [guild_id]

        if application_id is not None:
            query += " AND s.application_id = ?"
            params.append(application_id)

        query += " ORDER BY s.submitted_at ASC"

        rows = await self.db.fetch_all(query, tuple(params))

        return [dict(row) for row in rows] if rows else None
    
    async def update_submission_status(
        self,
        submission_id: int,
        status: str
    ) -> bool:
        rows_affected = await self.db.execute(
            """
            UPDATE application_submissions
            SET status = ?
            WHERE id = ?
            """,
            (status, submission_id),
            row_count=True,
        )

        return bool(rows_affected)
    
    async def get_application_views( 
        self,
    ) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            """
            SELECT
                av.guild_id,
                av.channel_id,
                av.application_id,
                av.message_id,

                a.id AS app_id,
                a.guild_id AS app_guild_id,
                a.name AS app_name,
                a.description AS app_description,
                a.active AS app_active,
                a.current_wave AS app_current_wave,
                a.submission_forum_id AS app_submission_forum_id,
                a.submit_btn_label AS submit_btn_label
            FROM application_views AS av
            JOIN application AS a
                ON av.application_id = a.id
            """
        )

        return [
            {
                "guild_id": row["guild_id"],
                "channel_id": row["channel_id"],
                "application_id": row["application_id"],
                "message_id": row["message_id"],
                "application": {
                    "id": row["app_id"],
                    "guild_id": row["app_guild_id"],
                    "name": row["app_name"],
                    "description": row["app_description"],
                    "active": row["app_active"],
                    "current_wave": row["app_current_wave"],
                    "submission_forum_id": row["app_submission_forum_id"],
                    "submit_btn_label" : row["submit_btn_label"]
                },
            }
            for row in rows
        ]
    
    async def get_submission_result(
        self,
        guild_id: int,
        submission_id: int,
    ) -> Optional[Dict[str, Any]]:
        submission_row = await self.db.fetch_one(
            """
            SELECT s.*,
                a.id AS app_id,
                a.name AS app_name,
                a.description AS app_description,
                a.active AS app_active,
                a.current_wave AS app_current_wave,
                a.submission_forum_id AS app_submission_forum_id
            FROM application_submissions s
            JOIN application a
                ON a.id = s.application_id
            AND a.guild_id = s.guild_id
            WHERE s.id = ?
            AND s.guild_id = ?
            """,
            (submission_id, guild_id),
        )

        if submission_row is None:
            return None

        submission_row = dict(submission_row)

        rows = await self.db.fetch_all(
            """
            SELECT
                ag.id AS group_id,
                ag.name AS group_name,
                ag.description AS group_description,
                aga.position AS group_position,

                q.id AS question_id,
                q.label AS question_label,
                q.description AS question_description,
                q.placeholder AS question_placeholder,
                q.min_length AS question_min_length,
                q.max_length AS question_max_length,
                q."type" AS question_type,
                q.metadata AS question_metadata,
                agq.position AS question_position,

                ans.answer_value AS answer_value
            FROM application_group_assignments aga
            JOIN application_groups ag
                ON ag.id = aga.group_id
            AND ag.guild_id = aga.guild_id
            JOIN application_group_questions agq
                ON agq.group_id = ag.id
            AND agq.guild_id = ag.guild_id
            JOIN application_questions q
                ON q.id = agq.question_id
            AND q.guild_id = agq.guild_id
            LEFT JOIN application_submission_answers ans
                ON ans.submission_id = ?
            AND ans.question_id = q.id
            WHERE aga.guild_id = ?
            AND aga.application_id = ?
            ORDER BY
                aga.position,
                agq.position
            """,
            (submission_id, guild_id, submission_row["application_id"]),
        )

        groups: Dict[int, Dict[str, Any]] = {}
        group_order: List[int] = []

        for row in rows:
            row = dict(row)
            group_id = row["group_id"]

            if group_id not in groups:
                groups[group_id] = {
                    "id": group_id,
                    "name": row["group_name"],
                    "description": row["group_description"],
                    "position": row["group_position"],
                    "questions": [],
                }
                group_order.append(group_id)

            groups[group_id]["questions"].append({
                "id": row["question_id"],
                "label": row["question_label"],
                "description": row["question_description"],
                "placeholder": row["question_placeholder"],
                "min_length": row["question_min_length"],
                "max_length": row["question_max_length"],
                "type": row["question_type"],
                "metadata": row["question_metadata"],
                "position": row["question_position"],
                "answer": row["answer_value"],
            })

        return {
            "submission": {
                "id": submission_row["id"],
                "guild_id": submission_row["guild_id"],
                "application_id": submission_row["application_id"],
                "member_id": submission_row["member_id"],
                "wave": submission_row["wave"],
                "status": submission_row["status"],
                "submitted_at": submission_row["submitted_at"],
            },
            "application": {
                "id": submission_row["app_id"],
                "name": submission_row["app_name"],
                "description": submission_row["app_description"],
                "active": submission_row["app_active"],
                "current_wave": submission_row["app_current_wave"],
                "submission_forum_id": submission_row["app_submission_forum_id"],
            },
            "groups": [groups[gid] for gid in group_order],
        }
    
    async def update_submission_verification_status(self, thread_id: int, tag: str):
        await self.db.execute(
            "UPDATE application_submissions SET verification_status = ? WHERE submission_thread_reference = ?"
        , (tag.lower(), thread_id) 
        )

    async def set_submission_thread_reference(self, submission_id: int, thread_id: int):
        await self.db.execute(
            "UPDATE application_submissions SET submission_thread_reference = ? WHERE id = ?"
        , (thread_id, submission_id) 
        )

    async def is_applicant_blocked(
        self,
        guild_id: int,
        member_id: int
    ) -> bool:
        await self.ensure_member(member_id, guild_id)
        row = await self.db.fetch_one(
            """
            SELECT 1
            FROM application_blocked_users
            WHERE guild_id = ?
            AND member_id = ?
            LIMIT 1
            """,
            (
                guild_id,
                member_id,
            ),
        )

        return row is not None

    async def update_applicant(
        self,
        guild_id: int,
        member_id: int,
        action_by: int,
        update: str,
        reason: str | None = None,
    ) -> None:
        await self.ensure_member(member_id, guild_id)
        if update == "block":
            await self.db.execute(
                """
                INSERT INTO application_blocked_users (
                    guild_id,
                    member_id,
                    blocked_by,
                    reason
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, member_id)
                DO UPDATE SET
                    blocked_by = excluded.blocked_by,
                    reason = excluded.reason,
                    blocked_at = datetime('now')
                """,
                (
                    guild_id,
                    member_id,
                    action_by,
                    reason,
                ),
            )

        elif update == "unblock":
            await self.db.execute(
                """
                DELETE FROM application_blocked_users
                WHERE guild_id = ?
                AND member_id = ?
                """,
                (
                    guild_id,
                    member_id,
                ),
            )

        else:
            raise ValueError(f"Unknown update action: {update}")

    async def get_applicant_status(
        self,
        guild_id: int,
        member_id: int
    ):
        block_row = await self.db.fetch_one(
            """
            SELECT reason, blocked_by, blocked_at
            FROM application_blocked_users
            WHERE guild_id = ? AND member_id = ?
            """,
            (guild_id, member_id),
        )

        block_status = {
            "blocked": block_row is not None,
            "reason": block_row["reason"] if block_row else None,
            "blocked_by": block_row["blocked_by"] if block_row else None,
            "blocked_at": block_row["blocked_at"] if block_row else None,
        }

        submissions = await self.db.fetch_all(
            """
            SELECT
                s.id AS submission_id,
                s.application_id,
                a.name AS application_name,
                s.wave,
                s.status,
                s.verification_status,
                s.submitted_at
            FROM application_submissions s
            JOIN application a ON a.id = s.application_id
            WHERE s.guild_id = ? AND s.member_id = ?
            ORDER BY s.submitted_at DESC
            """,
            (guild_id, member_id),
        )

        applications = []

        for sub in submissions:
            entry = {
                "application_id": sub["application_id"],
                "application_name": sub["application_name"],
                "submission_id": sub["submission_id"],
                "wave": sub["wave"],
                "status": sub["status"],
                "verification_status": sub["verification_status"],
                "submitted_at": sub["submitted_at"],
                "answers": None,
            }

            questions = await self.db.fetch_all(
                """
                SELECT
                    q.id AS question_id,
                    q.label,
                    q.description,
                    q.type,
                    ans.answer_value
                FROM application_group_assignments ga
                JOIN application_group_questions gq
                    ON gq.group_id = ga.group_id
                JOIN application_questions q
                    ON q.id = gq.question_id
                LEFT JOIN application_submission_answers ans
                    ON ans.question_id = q.id
                    AND ans.submission_id = ?
                WHERE ga.application_id = ?
                ORDER BY ga.position, gq.position
                """,
                (sub["submission_id"], sub["application_id"]),
            )

            entry["answers"] = [
                {
                    "question_id": q["question_id"],
                    "label": q["label"],
                    "description": q["description"],
                    "type": q["type"],
                    "answer_value": q["answer_value"], 
                }
                for q in questions
            ]

            applications.append(entry)

        return {
            "block_status": block_status,
            "applications": applications,
        }