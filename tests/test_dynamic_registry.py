"""
Unit tests for the Dynamic Semantic Registry.

Tests cover:
- Registry building from data
- Entity extraction (departments, accounts, subsidiaries)
- Alias generation
- Lookup and matching
- Cache persistence
- Clarification handling
"""
import pytest
import json
from pathlib import Path
from datetime import datetime, timedelta
from src.core.dynamic_registry import (
    DynamicRegistry,
    EntityType,
    RegistryEntry,
    RegistryMatch,
    get_dynamic_registry,
    reset_dynamic_registry,
)


@pytest.fixture
def sample_data():
    """Sample NetSuite data for testing."""
    return [
        {
            "department_name": "G&A (Parent) : Finance",
            "account_name": "Sales & Marketing : Employee Costs",
            "account_number": "531000",
            "subsidiarynohierarchy": "Phenom People Inc",
            "type": "Journal",
        },
        {
            "department_name": "G&A (Parent) : IT",
            "account_name": "G&A : Professional Services",
            "account_number": "591000",
            "subsidiarynohierarchy": "Phenom People Inc",
            "type": "VendBill",
        },
        {
            "department_name": "Sales & Marketing (Parent) : GPS - North America",
            "account_name": "Sales & Marketing : Travel",
            "account_number": "532000",
            "subsidiarynohierarchy": "Phenom People Inc",
            "type": "ExpRept",
        },
        {
            "department_name": "Sales & Marketing (Parent) : GPS - EMEA",
            "account_name": "Sales & Marketing : Travel",
            "account_number": "532000",
            "subsidiarynohierarchy": "Phenom People Netherlands BV",
            "type": "ExpRept",
        },
        {
            "department_name": "R&D (Parent) : Engineering",
            "account_name": "R&D : Cloud Hosting",
            "account_number": "521000",
            "subsidiarynohierarchy": "Phenom People Private Limited",
            "type": "VendBill",
        },
    ]


@pytest.fixture
def registry(tmp_path, sample_data):
    """Create a registry with sample data."""
    reset_dynamic_registry()
    reg = DynamicRegistry(cache_dir=tmp_path)
    reg.build_from_data(sample_data, force_rebuild=True)
    return reg


class TestRegistryBuilding:
    """Tests for registry building from data."""
    
    def test_build_extracts_departments(self, registry):
        """Should extract all unique departments."""
        depts = registry.get_all(EntityType.DEPARTMENT)
        assert len(depts) == 5  # 5 unique departments in sample data
        
        canonical_names = [d.canonical_name for d in depts]
        assert "G&A (Parent) : Finance" in canonical_names
        assert "G&A (Parent) : IT" in canonical_names
    
    def test_build_extracts_accounts(self, registry):
        """Should extract all unique accounts."""
        accounts = registry.get_all(EntityType.ACCOUNT)
        assert len(accounts) >= 3  # At least 3 unique account names
    
    def test_build_extracts_subsidiaries(self, registry):
        """Should extract all unique subsidiaries."""
        subs = registry.get_all(EntityType.SUBSIDIARY)
        assert len(subs) == 3  # 3 unique subsidiaries
        
        canonical_names = [s.canonical_name for s in subs]
        assert "Phenom People Inc" in canonical_names
        assert "Phenom People Netherlands BV" in canonical_names
    
    def test_build_generates_aliases(self, registry):
        """Should generate useful aliases for entries."""
        match = registry.lookup("Finance", EntityType.DEPARTMENT)
        assert not match.is_empty
        assert "finance" in match.best_match.aliases


class TestLookup:
    """Tests for registry lookup functionality."""
    
    def test_exact_match(self, registry):
        """Should find exact matches with high confidence."""
        match = registry.lookup("G&A (Parent) : Finance", EntityType.DEPARTMENT)
        assert match.is_exact
        assert match.confidence >= 0.95
    
    def test_alias_match(self, registry):
        """Should find matches via aliases."""
        match = registry.lookup("finance", EntityType.DEPARTMENT)
        assert not match.is_empty
        assert "Finance" in match.best_match.canonical_name
    
    def test_partial_match(self, registry):
        """Should find partial matches."""
        match = registry.lookup("GPS", EntityType.DEPARTMENT)
        assert not match.is_empty
        # Should find GPS - North America and GPS - EMEA
    
    def test_multiple_matches_need_clarification(self, registry):
        """Should request clarification for ambiguous terms."""
        match = registry.lookup("GPS", EntityType.DEPARTMENT)
        assert match.needs_clarification
        assert len(match.matches) >= 2
        assert len(match.clarification_options) >= 2
    
    def test_no_match_returns_empty(self, registry):
        """Should return empty match for unknown terms."""
        match = registry.lookup("NonExistentDepartment123", EntityType.DEPARTMENT)
        assert match.is_empty
        assert not match.needs_clarification
    
    def test_subsidiary_lookup(self, registry):
        """Should find subsidiaries."""
        match = registry.lookup("Netherlands", EntityType.SUBSIDIARY)
        assert not match.is_empty
        assert "Netherlands" in match.best_match.canonical_name


class TestCaching:
    """Tests for cache persistence."""
    
    def test_saves_to_cache(self, tmp_path, sample_data):
        """Should save registry to cache file."""
        reg = DynamicRegistry(cache_dir=tmp_path)
        reg.build_from_data(sample_data, force_rebuild=True)
        
        cache_file = tmp_path / "dynamic_registry.json"
        assert cache_file.exists()
        
        with open(cache_file) as f:
            cache_data = json.load(f)
        
        assert "registry" in cache_data
        assert "department" in cache_data["registry"]
    
    def test_loads_from_cache(self, tmp_path, sample_data):
        """Should load registry from cache on init."""
        # Build and save
        reg1 = DynamicRegistry(cache_dir=tmp_path)
        reg1.build_from_data(sample_data, force_rebuild=True)
        
        # Load from cache
        reg2 = DynamicRegistry(cache_dir=tmp_path)
        
        assert not reg2.is_empty()
        assert reg2.stats["departments"] == reg1.stats["departments"]
    
    def test_needs_refresh_when_stale(self, tmp_path, sample_data):
        """Should need refresh when cache is older than TTL."""
        reg = DynamicRegistry(cache_dir=tmp_path)
        reg.build_from_data(sample_data, force_rebuild=True)
        
        # Artificially age the cache
        reg._built_at = datetime.now() - timedelta(hours=25)
        
        assert reg.needs_refresh()


class TestAliasGeneration:
    """Tests for alias generation."""
    
    def test_generates_lowercase(self, registry):
        """Should include lowercase version."""
        entry = registry._registry[EntityType.DEPARTMENT].get("G&A (Parent) : Finance")
        assert "g&a (parent) : finance" in entry.aliases
    
    def test_generates_parts(self, registry):
        """Should include parts split by separator."""
        entry = registry._registry[EntityType.DEPARTMENT].get("G&A (Parent) : Finance")
        assert "finance" in entry.aliases
        assert "g&a" in entry.aliases
    
    def test_generates_abbreviations(self, registry):
        """Should include common abbreviations."""
        # Check if "ga" is generated for "G&A"
        match = registry.lookup("ga", EntityType.DEPARTMENT)
        # Should find G&A departments
        assert not match.is_empty
