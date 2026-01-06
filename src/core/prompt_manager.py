"""
Prompt Management System

Provides versioned, externalized prompt management with:
- YAML-based prompt definitions
- Version tracking
- A/B testing support
- Audit trail for prompt changes

Usage:
    from src.core.prompt_manager import get_prompt_manager
    
    pm = get_prompt_manager()
    prompt = pm.get_prompt("financial_analysis")
    formatted = prompt.format(query=query, data_summary=data)
"""

import yaml
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    """A versioned prompt template."""
    name: str
    version: str
    description: str
    
    # The actual prompts
    system_prompt: str
    user_prompt_template: str
    
    # Metadata
    model_compatibility: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    author: Optional[str] = None
    changelog: Optional[str] = None
    
    # Template variables
    required_variables: List[str] = field(default_factory=list)
    optional_variables: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def hash(self) -> str:
        """Generate hash of prompt content for tracking."""
        content = f"{self.system_prompt}{self.user_prompt_template}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def format(self, **kwargs) -> str:
        """Format the user prompt template with provided variables."""
        # Check required variables
        missing = [v for v in self.required_variables if v not in kwargs]
        if missing:
            raise ValueError(f"Missing required variables: {missing}")
        
        # Apply defaults for optional variables
        all_vars = {**self.optional_variables, **kwargs}
        
        return self.user_prompt_template.format(**all_vars)
    
    @classmethod
    def from_yaml(cls, path: Path) -> "PromptTemplate":
        """Load prompt template from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        
        return cls(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            system_prompt=data["system_prompt"],
            user_prompt_template=data["user_prompt_template"],
            model_compatibility=data.get("model_compatibility", []),
            created_at=data.get("created_at"),
            author=data.get("author"),
            changelog=data.get("changelog"),
            required_variables=data.get("required_variables", []),
            optional_variables=data.get("optional_variables", {}),
        )
    
    def to_yaml(self, path: Path):
        """Save prompt template to YAML file."""
        data = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "user_prompt_template": self.user_prompt_template,
            "model_compatibility": self.model_compatibility,
            "created_at": self.created_at or datetime.utcnow().isoformat(),
            "author": self.author,
            "changelog": self.changelog,
            "required_variables": self.required_variables,
            "optional_variables": self.optional_variables,
        }
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


class PromptManager:
    """
    Manages versioned prompts with caching and version selection.
    
    Directory structure:
        config/prompts/
            financial_analysis/
                v1.0.yaml
                v1.1.yaml
            evaluation/
                v1.0.yaml
            reflection/
                v1.0.yaml
    """
    
    def __init__(self, prompts_dir: Path = None):
        self.prompts_dir = prompts_dir or Path("config/prompts")
        self._cache: Dict[str, PromptTemplate] = {}
        self._active_versions: Dict[str, str] = {}
        
        # Load active versions from config if exists
        self._load_active_versions()
    
    def _load_active_versions(self):
        """Load active version selections from config file."""
        config_path = self.prompts_dir / "active_versions.yaml"
        if config_path.exists():
            with open(config_path) as f:
                self._active_versions = yaml.safe_load(f) or {}
    
    def _save_active_versions(self):
        """Save active version selections to config file."""
        config_path = self.prompts_dir / "active_versions.yaml"
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(self._active_versions, f)
    
    def _find_latest_version(self, prompt_name: str) -> Optional[str]:
        """Find the latest version for a prompt."""
        prompt_dir = self.prompts_dir / prompt_name
        if not prompt_dir.exists():
            return None
        
        versions = []
        for f in prompt_dir.glob("v*.yaml"):
            # Extract version from filename (e.g., v1.0.yaml -> 1.0)
            version_str = f.stem[1:]  # Remove 'v' prefix
            try:
                # Parse as tuple for proper sorting (1.10 > 1.9)
                parts = tuple(int(p) for p in version_str.split('.'))
                versions.append((parts, version_str))
            except ValueError:
                continue
        
        if not versions:
            return None
        
        versions.sort(reverse=True)
        return versions[0][1]
    
    def get_prompt(
        self, 
        name: str, 
        version: str = None,
    ) -> PromptTemplate:
        """
        Get a prompt template by name and optional version.
        
        Args:
            name: Prompt name (e.g., "financial_analysis")
            version: Specific version (e.g., "1.0") or None for active/latest
        
        Returns:
            PromptTemplate instance
        """
        # Determine version to use
        if version is None:
            version = self._active_versions.get(name) or self._find_latest_version(name)
        
        if version is None:
            raise FileNotFoundError(f"No prompt versions found for '{name}'")
        
        # Check cache
        cache_key = f"{name}/v{version}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Load from file
        path = self.prompts_dir / name / f"v{version}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        
        template = PromptTemplate.from_yaml(path)
        self._cache[cache_key] = template
        
        logger.debug(f"Loaded prompt {name} v{version} (hash: {template.hash})")
        return template
    
    def set_active_version(self, name: str, version: str):
        """Set the active version for a prompt (for A/B testing)."""
        # Verify version exists
        path = self.prompts_dir / name / f"v{version}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt version not found: {path}")
        
        self._active_versions[name] = version
        self._save_active_versions()
        logger.info(f"Set active version for {name} to v{version}")
    
    def list_prompts(self) -> Dict[str, List[str]]:
        """List all available prompts and their versions."""
        result = {}
        
        if not self.prompts_dir.exists():
            return result
        
        for prompt_dir in self.prompts_dir.iterdir():
            if prompt_dir.is_dir() and not prompt_dir.name.startswith('.'):
                versions = []
                for f in prompt_dir.glob("v*.yaml"):
                    versions.append(f.stem[1:])  # Remove 'v' prefix
                if versions:
                    result[prompt_dir.name] = sorted(versions)
        
        return result
    
    def get_active_versions(self) -> Dict[str, str]:
        """Get currently active versions for all prompts."""
        return dict(self._active_versions)


# Global instance
_prompt_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """Get the global prompt manager instance."""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager

