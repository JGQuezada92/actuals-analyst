"""
Account Hierarchy Rollups

Provides parent/child account relationship handling for rollup reporting.
Supports:
- Fetching account hierarchy from NetSuite
- Building account tree structure
- Rollup aggregation (sum children to parents)
- Parent account grouping for reports

Key Concepts:
- Parent Account: A summary account that contains child accounts
- Child Account: A detail account that rolls up to a parent
- Rollup: Summing child account amounts to parent level
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class AccountNode:
    """
    Represents an account in the hierarchy tree.
    
    Each account can have a parent and multiple children.
    """
    account_id: str
    account_number: str
    account_name: str
    account_type: Optional[str] = None
    parent_id: Optional[str] = None
    parent_number: Optional[str] = None
    parent_name: Optional[str] = None
    
    # Tree relationships
    children: List['AccountNode'] = field(default_factory=list)
    is_summary: bool = False  # True if this is a summary/parent account
    level: int = 0  # Depth in the hierarchy (0 = root/top-level)
    
    # Amount data (populated during aggregation)
    direct_amount: float = 0.0  # Amount from this account only
    rollup_amount: float = 0.0  # Amount including all children
    
    def to_dict(self, include_children: bool = True) -> Dict[str, Any]:
        result = {
            "account_id": self.account_id,
            "account_number": self.account_number,
            "account_name": self.account_name,
            "account_type": self.account_type,
            "parent_id": self.parent_id,
            "parent_number": self.parent_number,
            "parent_name": self.parent_name,
            "is_summary": self.is_summary,
            "level": self.level,
            "direct_amount": self.direct_amount,
            "rollup_amount": self.rollup_amount,
            "child_count": len(self.children),
        }
        
        if include_children and self.children:
            result["children"] = [c.to_dict(include_children) for c in self.children]
        
        return result
    
    @property
    def has_children(self) -> bool:
        return len(self.children) > 0
    
    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0


@dataclass
class AccountHierarchy:
    """
    Complete account hierarchy structure.
    
    Provides tree-based access to accounts and rollup functionality.
    """
    # Root accounts (accounts with no parent)
    roots: List[AccountNode] = field(default_factory=list)
    
    # All accounts indexed by ID for quick lookup
    accounts_by_id: Dict[str, AccountNode] = field(default_factory=dict)
    accounts_by_number: Dict[str, AccountNode] = field(default_factory=dict)
    
    # Metadata
    total_accounts: int = 0
    max_depth: int = 0
    
    def get_account(self, account_id: str = None, account_number: str = None) -> Optional[AccountNode]:
        """Get an account by ID or number."""
        if account_id and account_id in self.accounts_by_id:
            return self.accounts_by_id[account_id]
        if account_number and account_number in self.accounts_by_number:
            return self.accounts_by_number[account_number]
        return None
    
    def get_children(self, account_id: str = None, account_number: str = None) -> List[AccountNode]:
        """Get all child accounts of a parent."""
        account = self.get_account(account_id, account_number)
        return account.children if account else []
    
    def get_descendants(self, account_id: str = None, account_number: str = None) -> List[AccountNode]:
        """Get all descendants (children, grandchildren, etc.) of an account."""
        account = self.get_account(account_id, account_number)
        if not account:
            return []
        
        descendants = []
        self._collect_descendants(account, descendants)
        return descendants
    
    def _collect_descendants(self, node: AccountNode, results: List[AccountNode]):
        """Recursively collect all descendants."""
        for child in node.children:
            results.append(child)
            self._collect_descendants(child, results)
    
    def get_path_to_root(self, account_id: str = None, account_number: str = None) -> List[AccountNode]:
        """Get the path from an account up to the root."""
        account = self.get_account(account_id, account_number)
        if not account:
            return []
        
        path = [account]
        current = account
        
        while current.parent_id:
            parent = self.accounts_by_id.get(current.parent_id)
            if parent:
                path.append(parent)
                current = parent
            else:
                break
        
        return list(reversed(path))  # Root to leaf order
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_accounts": self.total_accounts,
            "max_depth": self.max_depth,
            "root_count": len(self.roots),
            "roots": [r.to_dict() for r in self.roots],
        }


class AccountHierarchyBuilder:
    """
    Builds the account hierarchy from raw NetSuite data.
    
    Fetches account data including parent relationships and constructs
    the tree structure.
    """
    
    # SuiteQL query to fetch account hierarchy
    ACCOUNT_QUERY = """
        SELECT
            Account.ID AS account_id,
            Account.AccountNumber AS account_number,
            Account.Name AS account_name,
            Account.Type AS account_type,
            Account.Parent AS parent_id,
            ParentAccount.AccountNumber AS parent_number,
            ParentAccount.Name AS parent_name,
            Account.IsSummary AS is_summary
        FROM
            Account
        LEFT JOIN
            Account AS ParentAccount ON ParentAccount.ID = Account.Parent
        WHERE
            Account.IsInactive = 'F'
        ORDER BY
            Account.AccountNumber
    """
    
    def __init__(self, netsuite_client=None):
        self._client = netsuite_client
        self._hierarchy_cache: Optional[AccountHierarchy] = None
    
    @property
    def client(self):
        """Lazy-load NetSuite client."""
        if self._client is None:
            from src.tools.netsuite_client import get_netsuite_client
            self._client = get_netsuite_client()
        return self._client
    
    def build(self, force_refresh: bool = False) -> AccountHierarchy:
        """
        Build the account hierarchy.
        
        Args:
            force_refresh: If True, fetch fresh data even if cached
        
        Returns:
            AccountHierarchy with complete tree structure
        """
        if self._hierarchy_cache and not force_refresh:
            return self._hierarchy_cache
        
        try:
            # Fetch account data
            result = self.client.execute_suiteql(self.ACCOUNT_QUERY)
            
            if not result or not result.get("items"):
                logger.warning("No account data retrieved")
                return AccountHierarchy()
            
            # Build hierarchy from raw data
            hierarchy = self._build_from_data(result["items"])
            self._hierarchy_cache = hierarchy
            
            logger.info(
                f"Built account hierarchy: {hierarchy.total_accounts} accounts, "
                f"{len(hierarchy.roots)} roots, max depth {hierarchy.max_depth}"
            )
            
            return hierarchy
            
        except Exception as e:
            logger.error(f"Failed to build account hierarchy: {e}")
            return AccountHierarchy()
    
    def _build_from_data(self, raw_data: List[Dict[str, Any]]) -> AccountHierarchy:
        """Build hierarchy from raw account data."""
        # Create account nodes
        accounts_by_id: Dict[str, AccountNode] = {}
        accounts_by_number: Dict[str, AccountNode] = {}
        
        for row in raw_data:
            account_id = str(row.get("account_id", ""))
            account_number = str(row.get("account_number", "") or "")
            
            node = AccountNode(
                account_id=account_id,
                account_number=account_number,
                account_name=str(row.get("account_name", "") or ""),
                account_type=str(row.get("account_type", "") or ""),
                parent_id=str(row.get("parent_id", "") or "") or None,
                parent_number=str(row.get("parent_number", "") or "") or None,
                parent_name=str(row.get("parent_name", "") or "") or None,
                is_summary=str(row.get("is_summary", "F")).upper() == "T",
            )
            
            accounts_by_id[account_id] = node
            if account_number:
                accounts_by_number[account_number] = node
        
        # Build tree relationships
        roots = []
        for node in accounts_by_id.values():
            if node.parent_id and node.parent_id in accounts_by_id:
                parent = accounts_by_id[node.parent_id]
                parent.children.append(node)
            else:
                roots.append(node)
        
        # Calculate levels
        max_depth = 0
        for root in roots:
            depth = self._calculate_levels(root, 0)
            max_depth = max(max_depth, depth)
        
        # Sort children by account number
        for node in accounts_by_id.values():
            node.children.sort(key=lambda x: x.account_number)
        
        return AccountHierarchy(
            roots=sorted(roots, key=lambda x: x.account_number),
            accounts_by_id=accounts_by_id,
            accounts_by_number=accounts_by_number,
            total_accounts=len(accounts_by_id),
            max_depth=max_depth,
        )
    
    def _calculate_levels(self, node: AccountNode, current_level: int) -> int:
        """Recursively calculate levels and return max depth."""
        node.level = current_level
        
        if not node.children:
            return current_level
        
        max_child_depth = current_level
        for child in node.children:
            child_depth = self._calculate_levels(child, current_level + 1)
            max_child_depth = max(max_child_depth, child_depth)
        
        return max_child_depth


class RollupAggregator:
    """
    Aggregates financial data with parent/child rollups.
    
    Takes transaction-level data and aggregates it by account,
    rolling up child account amounts to their parents.
    """
    
    def __init__(self, hierarchy: AccountHierarchy = None):
        self._hierarchy = hierarchy
        self._builder = AccountHierarchyBuilder()
    
    @property
    def hierarchy(self) -> AccountHierarchy:
        """Get or build the account hierarchy."""
        if self._hierarchy is None:
            self._hierarchy = self._builder.build()
        return self._hierarchy
    
    def aggregate_with_rollup(
        self,
        data: List[Dict[str, Any]],
        amount_field: str = None,
        account_field: str = None,
    ) -> Dict[str, AccountNode]:
        """
        Aggregate data with rollup to parent accounts.
        
        Args:
            data: List of transaction data
            amount_field: Name of the amount field (auto-detected if None)
            account_field: Name of the account number field (auto-detected if None)
        
        Returns:
            Dict mapping account numbers to AccountNode with amounts
        """
        hierarchy = self.hierarchy
        
        # Auto-detect fields
        if data and (not amount_field or not account_field):
            sample = data[0]
            for key in sample.keys():
                key_lower = key.lower()
                if not amount_field and "amount" in key_lower:
                    amount_field = key
                if not account_field and "account" in key_lower and "number" in key_lower:
                    account_field = key
        
        if not amount_field or not account_field:
            logger.warning("Could not detect amount or account fields")
            return {}
        
        # Reset amounts
        for node in hierarchy.accounts_by_id.values():
            node.direct_amount = 0.0
            node.rollup_amount = 0.0
        
        # Aggregate direct amounts by account
        for row in data:
            account_number = str(row.get(account_field, "") or "")
            amount = float(row.get(amount_field, 0) or 0)
            
            node = hierarchy.get_account(account_number=account_number)
            if node:
                node.direct_amount += amount
        
        # Calculate rollup amounts (bottom-up)
        for root in hierarchy.roots:
            self._calculate_rollup(root)
        
        return hierarchy.accounts_by_number
    
    def _calculate_rollup(self, node: AccountNode) -> float:
        """
        Recursively calculate rollup amounts.
        
        Returns the rollup amount for this node.
        """
        # Start with direct amount
        rollup = node.direct_amount
        
        # Add children's rollup amounts
        for child in node.children:
            rollup += self._calculate_rollup(child)
        
        node.rollup_amount = rollup
        return rollup
    
    def get_summary_by_parent(
        self,
        data: List[Dict[str, Any]],
        parent_level: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get a summary aggregated to a specific parent level.
        
        Args:
            data: List of transaction data
            parent_level: Level of parents to aggregate to (0 = top-level)
        
        Returns:
            List of summary records at the specified level
        """
        self.aggregate_with_rollup(data)
        hierarchy = self.hierarchy
        
        # Collect accounts at the target level
        results = []
        for root in hierarchy.roots:
            self._collect_at_level(root, parent_level, results)
        
        return results
    
    def _collect_at_level(
        self,
        node: AccountNode,
        target_level: int,
        results: List[Dict[str, Any]],
    ):
        """Collect accounts at a specific level."""
        if node.level == target_level:
            results.append({
                "account_number": node.account_number,
                "account_name": node.account_name,
                "account_type": node.account_type,
                "direct_amount": node.direct_amount,
                "rollup_amount": node.rollup_amount,
                "child_count": len(node.children),
            })
        elif node.level < target_level:
            for child in node.children:
                self._collect_at_level(child, target_level, results)


def format_hierarchy_report(
    aggregator: RollupAggregator,
    indent_size: int = 2,
) -> str:
    """Format the hierarchy as a text report with indentation."""
    lines = ["Account Hierarchy with Rollups", "=" * 50, ""]
    
    for root in aggregator.hierarchy.roots:
        _format_node(root, lines, 0, indent_size)
    
    return "\n".join(lines)


def _format_node(node: AccountNode, lines: List[str], depth: int, indent_size: int):
    """Recursively format a node and its children."""
    indent = " " * (depth * indent_size)
    
    if node.rollup_amount != 0:
        lines.append(
            f"{indent}{node.account_number} - {node.account_name}: "
            f"${node.rollup_amount:,.2f}"
        )
        if node.has_children and node.direct_amount != 0:
            lines.append(f"{indent}  (direct: ${node.direct_amount:,.2f})")
    
    for child in node.children:
        _format_node(child, lines, depth + 1, indent_size)


# Singleton instances
_hierarchy_builder: Optional[AccountHierarchyBuilder] = None
_rollup_aggregator: Optional[RollupAggregator] = None


def get_account_hierarchy_builder() -> AccountHierarchyBuilder:
    """Get the account hierarchy builder instance."""
    global _hierarchy_builder
    if _hierarchy_builder is None:
        _hierarchy_builder = AccountHierarchyBuilder()
    return _hierarchy_builder


def get_rollup_aggregator() -> RollupAggregator:
    """Get the rollup aggregator instance."""
    global _rollup_aggregator
    if _rollup_aggregator is None:
        _rollup_aggregator = RollupAggregator()
    return _rollup_aggregator

