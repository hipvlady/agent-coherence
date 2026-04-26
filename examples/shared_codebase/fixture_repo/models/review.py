"""Product review domain model."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class ReviewStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED = "flagged"


class ReviewHelpfulness(Enum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"


@dataclass
class ReviewVote:
    user_id: int
    vote: ReviewHelpfulness
    created_at: datetime


@dataclass
class ReviewImage:
    url: str
    caption: Optional[str] = None


@dataclass
class Review:
    id: int
    product_id: int
    user_id: int
    order_id: Optional[int]
    rating: int
    title: str
    body: str
    status: ReviewStatus
    created_at: datetime
    updated_at: datetime
    verified_purchase: bool = False
    votes: list[ReviewVote] = field(default_factory=list)
    images: list[ReviewImage] = field(default_factory=list)
    admin_notes: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not 1 <= self.rating <= 5:
            errors.append(f"rating must be 1-5, got {self.rating}")
        if len(self.title) < 3:
            errors.append("title too short (min 3 chars)")
        if len(self.title) > 120:
            errors.append("title too long (max 120 chars)")
        if len(self.body) < 10:
            errors.append("body too short (min 10 chars)")
        if len(self.body) > 5000:
            errors.append("body too long (max 5000 chars)")
        return errors

    def approve(self) -> None:
        if self.status not in (ReviewStatus.PENDING, ReviewStatus.FLAGGED):
            raise ValueError(f"cannot approve review in {self.status.value} state")
        self.status = ReviewStatus.APPROVED
        self.updated_at = datetime.utcnow()

    def reject(self, reason: str) -> None:
        self.status = ReviewStatus.REJECTED
        self.admin_notes = reason
        self.updated_at = datetime.utcnow()

    def flag(self, reason: str) -> None:
        if self.status == ReviewStatus.REJECTED:
            raise ValueError("cannot flag rejected review")
        self.status = ReviewStatus.FLAGGED
        self.admin_notes = reason
        self.updated_at = datetime.utcnow()

    def add_vote(self, user_id: int, vote: ReviewHelpfulness) -> None:
        existing = next((v for v in self.votes if v.user_id == user_id), None)
        if existing:
            existing.vote = vote
        else:
            self.votes.append(ReviewVote(user_id=user_id, vote=vote,
                                         created_at=datetime.utcnow()))

    @property
    def helpfulness_score(self) -> float:
        if not self.votes:
            return 0.0
        helpful = sum(1 for v in self.votes if v.vote == ReviewHelpfulness.HELPFUL)
        return helpful / len(self.votes)
