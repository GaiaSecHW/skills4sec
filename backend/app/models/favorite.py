from tortoise import fields
from tortoise.models import Model


class UserFavorite(Model):
    """用户收藏模型"""
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="favorites", on_delete=fields.CASCADE)
    skill_slug = fields.CharField(max_length=191, description="技能 slug")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_favorites"
        unique_together = (("user_id", "skill_slug"),)
        indexes = [
            ("user_id",),
            ("skill_slug",),
        ]

    def __str__(self):
        return f"UserFavorite(user_id={self.user_id}, slug={self.skill_slug})"
