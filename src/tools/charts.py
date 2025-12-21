"""
Chart Generation Tools

Creates professional charts and visualizations for Slack output.
Charts are generated as PNG files that can be uploaded to Slack.
"""
import os
import io
import base64
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class ChartOutput:
    """Container for a generated chart."""
    chart_type: str
    title: str
    file_path: str
    file_bytes: bytes
    width: int
    height: int
    alt_text: str  # Accessibility description
    
    def to_base64(self) -> str:
        """Convert to base64 for embedding."""
        return base64.b64encode(self.file_bytes).decode('utf-8')

class ChartGenerator:
    """
    Professional chart generation for financial data.
    
    Uses matplotlib for generation, styled for professional reports.
    """
    
    def __init__(self, output_dir: str = ".charts"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Import and configure matplotlib
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            import matplotlib.pyplot as plt
            import matplotlib.ticker as mticker
            self.plt = plt
            self.mticker = mticker
            
            # Set professional style
            plt.style.use('seaborn-v0_8-whitegrid')
            plt.rcParams.update({
                'font.family': 'sans-serif',
                'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
                'font.size': 10,
                'axes.titlesize': 12,
                'axes.labelsize': 10,
                'xtick.labelsize': 9,
                'ytick.labelsize': 9,
                'legend.fontsize': 9,
                'figure.titlesize': 14,
                'figure.dpi': 150,
                'savefig.dpi': 150,
                'savefig.bbox': 'tight',
                'axes.spines.top': False,
                'axes.spines.right': False,
            })
        except ImportError:
            raise ImportError("Install matplotlib: pip install matplotlib")
    
    def _save_chart(self, fig, title: str, chart_type: str) -> ChartOutput:
        """Save figure and return ChartOutput."""
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() else "_" for c in title)[:50]
        filename = f"{chart_type}_{safe_title}_{timestamp}.png"
        file_path = self.output_dir / filename
        
        # Save to file
        fig.savefig(file_path, format='png', bbox_inches='tight', facecolor='white')
        
        # Also get bytes
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        buf.seek(0)
        file_bytes = buf.read()
        
        # Get dimensions
        width, height = fig.get_size_inches() * fig.dpi
        
        self.plt.close(fig)
        
        return ChartOutput(
            chart_type=chart_type,
            title=title,
            file_path=str(file_path),
            file_bytes=file_bytes,
            width=int(width),
            height=int(height),
            alt_text=f"{chart_type} chart showing {title}",
        )
    
    def bar_chart(
        self,
        categories: List[str],
        values: List[float],
        title: str,
        xlabel: str = "",
        ylabel: str = "",
        color: str = "#2E86AB",
        horizontal: bool = False,
        show_values: bool = True,
        value_format: str = "${:,.0f}",
    ) -> ChartOutput:
        """Create a bar chart."""
        fig, ax = self.plt.subplots(figsize=(10, 6))
        
        if horizontal:
            bars = ax.barh(categories, values, color=color)
            ax.set_xlabel(ylabel or "Value")
            ax.set_ylabel(xlabel or "Category")
            
            if show_values:
                for bar, val in zip(bars, values):
                    ax.text(
                        bar.get_width() + max(values) * 0.01,
                        bar.get_y() + bar.get_height() / 2,
                        value_format.format(val),
                        va='center',
                        fontsize=9,
                    )
        else:
            bars = ax.bar(categories, values, color=color)
            ax.set_xlabel(xlabel or "Category")
            ax.set_ylabel(ylabel or "Value")
            
            # Rotate labels if needed
            if len(categories) > 5 or any(len(str(c)) > 10 for c in categories):
                self.plt.xticks(rotation=45, ha='right')
            
            if show_values:
                for bar, val in zip(bars, values):
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + max(values) * 0.01,
                        value_format.format(val),
                        ha='center',
                        fontsize=9,
                    )
        
        ax.set_title(title, fontweight='bold', pad=20)
        
        # Format y-axis for currency
        if "$" in value_format:
            ax.yaxis.set_major_formatter(
                self.mticker.FuncFormatter(lambda x, p: f"${x/1000:,.0f}K" if x >= 1000 else f"${x:,.0f}")
            )
        
        self.plt.tight_layout()
        return self._save_chart(fig, title, "bar")
    
    def line_chart(
        self,
        x_values: List[Any],
        y_values: List[float],
        title: str,
        xlabel: str = "",
        ylabel: str = "",
        color: str = "#2E86AB",
        show_markers: bool = True,
        fill_area: bool = False,
        comparison_line: Optional[Tuple[List[Any], List[float], str]] = None,
    ) -> ChartOutput:
        """Create a line chart with optional comparison."""
        fig, ax = self.plt.subplots(figsize=(10, 6))
        
        marker = 'o' if show_markers else None
        ax.plot(x_values, y_values, color=color, marker=marker, linewidth=2, markersize=6, label="Actual")
        
        if fill_area:
            ax.fill_between(x_values, y_values, alpha=0.3, color=color)
        
        if comparison_line:
            comp_x, comp_y, comp_label = comparison_line
            ax.plot(comp_x, comp_y, color='#E94F37', linestyle='--', linewidth=2, label=comp_label)
            ax.legend()
        
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontweight='bold', pad=20)
        
        # Rotate x labels if dates or many items
        if len(x_values) > 6:
            self.plt.xticks(rotation=45, ha='right')
        
        # Format y-axis for currency
        ax.yaxis.set_major_formatter(
            self.mticker.FuncFormatter(lambda x, p: f"${x/1000:,.0f}K" if x >= 1000 else f"${x:,.0f}")
        )
        
        self.plt.tight_layout()
        return self._save_chart(fig, title, "line")
    
    def pie_chart(
        self,
        categories: List[str],
        values: List[float],
        title: str,
        colors: Optional[List[str]] = None,
        show_percentages: bool = True,
        explode_top: bool = False,
    ) -> ChartOutput:
        """Create a pie chart."""
        fig, ax = self.plt.subplots(figsize=(10, 8))
        
        # Default color palette
        if colors is None:
            colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#3B1F2B', 
                     '#95A3B3', '#6B9AC4', '#D4A373', '#E9C46A', '#2A9D8F']
        
        # Explode largest slice if requested
        explode = None
        if explode_top:
            max_idx = values.index(max(values))
            explode = [0.05 if i == max_idx else 0 for i in range(len(values))]
        
        autopct = '%1.1f%%' if show_percentages else None
        
        wedges, texts, autotexts = ax.pie(
            values,
            labels=categories,
            colors=colors[:len(categories)],
            explode=explode,
            autopct=autopct,
            pctdistance=0.75,
            startangle=90,
        )
        
        # Style percentage labels
        if show_percentages:
            for autotext in autotexts:
                autotext.set_fontsize(9)
                autotext.set_fontweight('bold')
        
        ax.set_title(title, fontweight='bold', pad=20)
        
        self.plt.tight_layout()
        return self._save_chart(fig, title, "pie")
    
    def variance_chart(
        self,
        categories: List[str],
        actual: List[float],
        budget: List[float],
        title: str,
    ) -> ChartOutput:
        """Create a variance chart comparing actual vs budget."""
        fig, ax = self.plt.subplots(figsize=(12, 6))
        
        x = range(len(categories))
        width = 0.35
        
        bars1 = ax.bar([i - width/2 for i in x], actual, width, label='Actual', color='#2E86AB')
        bars2 = ax.bar([i + width/2 for i in x], budget, width, label='Budget', color='#95A3B3')
        
        ax.set_xlabel('Category')
        ax.set_ylabel('Amount')
        ax.set_title(title, fontweight='bold', pad=20)
        ax.set_xticks(x)
        ax.set_xticklabels(categories, rotation=45, ha='right')
        ax.legend()
        
        # Add variance annotations
        for i, (a, b) in enumerate(zip(actual, budget)):
            variance = a - b
            pct = (variance / b * 100) if b != 0 else 0
            color = '#2A9D8F' if variance >= 0 else '#E94F37'
            symbol = '+' if variance >= 0 else ''
            ax.annotate(
                f'{symbol}{pct:.1f}%',
                xy=(i, max(a, b) + max(actual) * 0.02),
                ha='center',
                fontsize=8,
                color=color,
                fontweight='bold',
            )
        
        # Format y-axis
        ax.yaxis.set_major_formatter(
            self.mticker.FuncFormatter(lambda x, p: f"${x/1000:,.0f}K" if x >= 1000 else f"${x:,.0f}")
        )
        
        self.plt.tight_layout()
        return self._save_chart(fig, title, "variance")
    
    def waterfall_chart(
        self,
        categories: List[str],
        values: List[float],
        title: str,
        start_label: str = "Start",
        end_label: str = "End",
    ) -> ChartOutput:
        """Create a waterfall chart showing cumulative changes."""
        fig, ax = self.plt.subplots(figsize=(12, 6))
        
        # Calculate running total
        running_total = [0]
        for v in values:
            running_total.append(running_total[-1] + v)
        
        # Add start and end bars
        all_categories = [start_label] + categories + [end_label]
        
        # Colors for positive/negative
        colors = ['#95A3B3']  # Start bar
        for v in values:
            colors.append('#2A9D8F' if v >= 0 else '#E94F37')
        colors.append('#2E86AB')  # End bar
        
        # Calculate bar positions
        bottoms = [0]  # Start at 0
        heights = [running_total[1]]  # First actual value
        
        for i in range(len(values)):
            if values[i] >= 0:
                bottoms.append(running_total[i + 1] - values[i])
                heights.append(values[i])
            else:
                bottoms.append(running_total[i + 1])
                heights.append(-values[i])
        
        bottoms.append(0)  # End bar starts at 0
        heights.append(running_total[-1])
        
        # Plot
        ax.bar(all_categories, heights, bottom=bottoms, color=colors)
        
        # Add connecting lines
        for i in range(len(all_categories) - 1):
            ax.plot(
                [i + 0.4, i + 0.6],
                [running_total[i + 1], running_total[i + 1]],
                'k-',
                linewidth=1,
            )
        
        # Add value labels
        for i, (cat, h, b) in enumerate(zip(all_categories, heights, bottoms)):
            val = h if i == 0 or i == len(all_categories) - 1 else (values[i-1] if i > 0 and i <= len(values) else h)
            ax.text(
                i, b + h + max(heights) * 0.02,
                f"${val:,.0f}",
                ha='center',
                fontsize=8,
            )
        
        ax.set_ylabel('Amount')
        ax.set_title(title, fontweight='bold', pad=20)
        self.plt.xticks(rotation=45, ha='right')
        
        ax.yaxis.set_major_formatter(
            self.mticker.FuncFormatter(lambda x, p: f"${x/1000:,.0f}K" if x >= 1000 else f"${x:,.0f}")
        )
        
        self.plt.tight_layout()
        return self._save_chart(fig, title, "waterfall")

# Factory function
def get_chart_generator(output_dir: str = ".charts") -> ChartGenerator:
    """Get a chart generator instance."""
    return ChartGenerator(output_dir)
