"""
Professional Financial Chart Styling

Centralized configuration for investment banking / corporate finance
quality visualizations. Derived from CFI financial modeling standards.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class ChartStyle(Enum):
    """Pre-defined chart styles."""
    PROFESSIONAL = "professional"  # IB/PE style
    MINIMAL = "minimal"            # Clean, simple
    PRESENTATION = "presentation"  # Bold for slides


@dataclass
class ColorPalette:
    """Professional color configuration."""
    # Primary colors
    primary: str = "#1E8496"           # Teal
    secondary: str = "#FA621C"         # Orange  
    accent: str = "#132E57"            # Navy
    highlight: str = "#ED942D"         # Gold
    
    # Semantic colors
    positive: str = "#00B050"          # Green
    negative: str = "#E94F37"          # Red
    neutral: str = "#808080"           # Gray
    
    # Background colors
    header_bg: str = "#132E57"         # Navy header
    alt_row_bg: str = "#F2F2F2"        # Alternating rows
    
    # Text colors
    text_light: str = "#FFFFFF"
    text_dark: str = "#132E57"
    text_muted: str = "#808080"
    
    # Chart series (ordered)
    series: List[str] = field(default_factory=lambda: [
        "#1E8496",  # Teal
        "#FA621C",  # Orange
        "#25A2AF",  # Light teal
        "#132E57",  # Navy
        "#ED942D",  # Gold
        "#00B050",  # Green
    ])


@dataclass  
class Typography:
    """Font configuration."""
    family: str = "Arial Narrow"
    fallback: str = "Arial"
    title_size: int = 14
    header_size: int = 12
    body_size: int = 11
    small_size: int = 10
    
    # Weights
    title_weight: str = "bold"
    header_weight: str = "bold"
    body_weight: str = "normal"


@dataclass
class ChartConfig:
    """Complete chart configuration."""
    colors: ColorPalette = field(default_factory=ColorPalette)
    typography: Typography = field(default_factory=Typography)
    
    # Chart dimensions
    default_width: int = 15           # Inches (Excel chart units)
    default_height: float = 7.5
    dpi: int = 150
    
    # Grid and axes
    show_gridlines: bool = False      # Professional charts often hide gridlines
    show_legend: bool = True
    legend_position: str = "top"      # 't' for top
    
    # Data labels
    show_data_labels: bool = True
    label_font_size: int = 9
    
    # Margins
    title_pad: int = 20
    
    def get_matplotlib_rcparams(self) -> Dict:
        """Get matplotlib rcParams for consistent styling."""
        return {
            'font.family': 'sans-serif',
            'font.sans-serif': [self.typography.family, self.typography.fallback, 'DejaVu Sans'],
            'font.size': self.typography.body_size,
            'axes.titlesize': self.typography.header_size,
            'axes.titleweight': self.typography.title_weight,
            'axes.labelsize': self.typography.body_size,
            'xtick.labelsize': self.typography.small_size,
            'ytick.labelsize': self.typography.small_size,
            'legend.fontsize': self.typography.small_size,
            'figure.titlesize': self.typography.title_size,
            'figure.dpi': self.dpi,
            'savefig.dpi': self.dpi,
            'savefig.bbox': 'tight',
            'axes.spines.top': False,
            'axes.spines.right': False,
            'axes.grid': self.show_gridlines,
            'axes.facecolor': 'white',
            'figure.facecolor': 'white',
        }


# Global instance
_chart_config: Optional[ChartConfig] = None

def get_chart_config() -> ChartConfig:
    """Get the global chart configuration."""
    global _chart_config
    if _chart_config is None:
        _chart_config = ChartConfig()
    return _chart_config

def set_chart_config(config: ChartConfig):
    """Set custom chart configuration."""
    global _chart_config
    _chart_config = config

