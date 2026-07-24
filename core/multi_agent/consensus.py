"""
Consensus Builder

Builds consensus among multiple agents through voting and discussion.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class VoteOption(str, Enum):
    """Standard vote options."""
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"
    BLANK = "blank"


@dataclass
class Vote:
    """A single vote."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    voter_id: str = ""
    voter_name: str = ""
    option: VoteOption = VoteOption.BLANK
    reasoning: str = ""
    weight: float = 1.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "voter_id": self.voter_id,
            "voter_name": self.voter_name,
            "option": self.option.value,
            "reasoning": self.reasoning,
            "weight": self.weight,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ConsensusResult:
    """Result of consensus building."""
    reached: bool
    decision: Optional[str] = None
    votes: list[Vote] = field(default_factory=list)
    tally: dict[str, int] = field(default_factory=dict)
    weighted_tally: dict[str, float] = field(default_factory=dict)
    discussion_rounds: int = 0
    dissenting_opinions: list[str] = field(default_factory=list)


class ConsensusBuilder:
    """
    Builds consensus among agents through structured voting.

    Features:
    - Proposal submission
    - Multiple voting rounds
    - Weighted voting
    - Discussion facilitation
    - Minority opinion tracking
    """

    def __init__(self, threshold: float = 0.5, rounds: int = 3):
        """
        Initialize consensus builder.

        Args:
            threshold: Agreement threshold (0.0-1.0)
            rounds: Maximum discussion rounds
        """
        self.threshold = threshold
        self.max_rounds = rounds
        self._current_proposal: Optional[str] = None
        self._votes: list[Vote] = []
        self._voters: dict[str, float] = {}  # voter_id -> weight

        logger.info("consensus_builder_initialized", threshold=threshold)

    def set_voters(self, voters: list[tuple[str, str, float]]) -> None:
        """
        Set the voters and their weights.

        Args:
            voters: List of (voter_id, voter_name, weight) tuples
        """
        self._voters = {v[0]: v[2] for v in voters}

    def submit_proposal(self, proposal: str) -> None:
        """Submit a proposal for voting."""
        self._current_proposal = proposal
        self._votes.clear()
        logger.debug("proposal_submitted", proposal=proposal[:100])

    def cast_vote(
        self,
        voter_id: str,
        option: VoteOption,
        reasoning: str = "",
    ) -> Optional[Vote]:
        """
        Cast a vote.

        Args:
            voter_id: ID of the voter
            option: Vote option
            reasoning: Optional reasoning for the vote

        Returns:
            Created Vote or None if voter not in list
        """
        if voter_id not in self._voters:
            return None

        if self._current_proposal is None:
            return None

        # Check for existing vote
        existing = next((v for v in self._votes if v.voter_id == voter_id), None)
        if existing:
            existing.option = option
            existing.reasoning = reasoning
            existing.timestamp = datetime.utcnow()
            return existing

        # Get voter name
        voter_name = voter_id  # Default to ID
        for vid, name, _ in [(k, k, v) for k, v in self._voters.items()]:
            if vid == voter_id:
                voter_name = f"Agent {voter_id[:8]}"
                break

        vote = Vote(
            voter_id=voter_id,
            voter_name=voter_name,
            option=option,
            reasoning=reasoning,
            weight=self._voters.get(voter_id, 1.0),
        )

        self._votes.append(vote)
        logger.debug("vote_cast", voter_id=voter_id, option=option.value)

        return vote

    def get_tally(self) -> tuple[dict[str, int], dict[str, float]]:
        """Get vote tallies (raw and weighted)."""
        tally = {opt.value: 0 for opt in VoteOption}
        weighted_tally = {opt.value: 0.0 for opt in VoteOption}

        for vote in self._votes:
            tally[vote.option.value] += 1
            weighted_tally[vote.option.value] += vote.weight

        return tally, weighted_tally

    def check_consensus(self) -> tuple[bool, Optional[str]]:
        """
        Check if consensus has been reached.

        Returns:
            Tuple of (reached, decision)
        """
        tally, weighted = self.get_tally()
        total_votes = len(self._votes)
        total_weight = sum(v.weight for v in self._votes)

        if total_votes == 0:
            return False, None

        # Calculate percentages
        yes_pct = weighted.get(VoteOption.YES.value, 0) / total_weight if total_weight > 0 else 0
        no_pct = weighted.get(VoteOption.NO.value, 0) / total_weight if total_weight > 0 else 0

        if yes_pct >= self.threshold:
            return True, "approved"

        if no_pct >= self.threshold:
            return True, "rejected"

        if self._votes and no_pct > yes_pct:
            return True, "rejected"

        return False, None

    def get_result(self) -> ConsensusResult:
        """Get the full consensus result."""
        tally, weighted = self.get_tally()
        reached, decision = self.check_consensus()

        # Collect dissenting opinions
        dissenting = [
            f"{v.voter_name}: {v.reasoning}"
            for v in self._votes
            if v.option == VoteOption.NO
        ]

        return ConsensusResult(
            reached=reached,
            decision=decision,
            votes=self._votes.copy(),
            tally=tally,
            weighted_tally=weighted,
            dissenting_opinions=dissenting,
        )

    def get_majority_opinion(self) -> Optional[Vote]:
        """Get the majority opinion (excluding abstains)."""
        non_abstain = [v for v in self._votes if v.option != VoteOption.ABSTAIN]
        if not non_abstain:
            return None

        # Weight by votes
        weighted_votes: dict[VoteOption, float] = {}
        for vote in non_abstain:
            weighted_votes[vote.option] = weighted_votes.get(vote.option, 0) + vote.weight

        if not weighted_votes:
            return None

        majority_option = max(weighted_votes, key=weighted_votes.get)

        # Get a vote with this option
        for vote in non_abstain:
            if vote.option == majority_option:
                return vote

        return None

    def clear(self) -> None:
        """Clear current proposal and votes."""
        self._current_proposal = None
        self._votes.clear()
