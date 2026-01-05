"""
Chart Generation Tools - Professional Financial Styling

Creates investment banking quality charts for financial analysis.
Supports PNG output for Slack and Excel embedding.
"""
import os
import io
import base64
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

from config.chart_styles import get_chart_config, ChartConfig

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
    
    Styled to match investment banking / corporate finance standards:
    - Arial Narrow typography
    - Teal/Navy/Orange color palette
    - Clean, minimal design
    - Accounting-style number formatting
    """
    
    def __init__(self, output_dir: str = ".charts", config: ChartConfig = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or get_chart_config()
        
        # Import and configure matplotlib
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            import matplotlib.pyplot as plt
            import matplotlib.ticker as mticker
            self.plt = plt
            self.mticker = mticker
            
            # Apply professional styling
            plt.rcParams.update(self.config.get_matplotlib_rcparams())
        except ImportError:
            raise ImportError("Install matplotlib: pip install matplotlib")
    
    def _get_series_color(self, index: int) -> str:
        """Get color for series by index."""
        colors = self.config.colors.series
        return colors[index % len(colors)]
    
    def _format_currency_axis(self, ax, axis='y'):
        """Apply accounting-style currency formatting to axis."""
        formatter = self.mticker.FuncFormatter(
            lambda x, p: f"${x/1e9:.1f}B" if abs(x) >= 1e9 
            else f"${x/1e6:.1f}M" if abs(x) >= 1e6 
            else f"${x/1e3:.0f}K" if abs(x) >= 1e3 
            else f"${x:,.0f}"
        )
        if axis == 'y':
            ax.yaxis.set_major_formatter(formatter)
        else:
            ax.xaxis.set_major_formatter(formatter)
    
    def _add_data_labels(self, ax, bars, values, format_str="${:,.0f}"):
        """Add data labels to bars."""
        for bar, val in zip(bars, values):
            height = bar.get_height()
            ax.annotate(
                format_str.format(val),
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha='center',
                va='bottom',
                fontsize=self.config.typography.small_size,
                fontweight='bold' if abs(val) > 0 else 'normal',
            )
    
    def _save_chart(self, fig, title: str, chart_type: str) -> ChartOutput:
        """Save figure and return ChartOutput."""
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() else "_" for c in title)[:50]
        filename = f"{chart_type}_{safe_title}_{timestamp}.png"
        file_path = self.output_dir / filename
        
        # Save to file
        fig.savefig(file_path, format='png', bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        
        # Also save to bytes
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight',
                   facecolor='white', edgecolor='none')
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
            alt_text=f"{chart_type.replace('_', ' ').title()}: {title}",
        )
    
    def bar_chart(
        self,
        categories: List[str],
        values: List[float],
        title: str,
        xlabel: str = "",
        ylabel: str = "",
        horizontal: bool = False,
        show_values: bool = True,
        color: str = None,
        value_format: str = "${:,.0f}",
    ) -> ChartOutput:
        """Create a professional bar chart."""
        fig, ax = self.plt.subplots(figsize=(10, 6))
        
        bar_color = color or self.config.colors.primary
        
        if horizontal:
            bars = ax.barh(categories, values, color=bar_color)
            ax.set_xlabel(ylabel or "Value")
            ax.set_ylabel(xlabel or "Category")
            
            if show_values:
                for bar, val in zip(bars, values):
                    ax.text(
                        bar.get_width() + max(values) * 0.01,
                        bar.get_y() + bar.get_height() / 2,
                        value_format.format(val),
                        va='center',
                        fontsize=self.config.typography.small_size,
                        fontweight='bold',
                    )
            self._format_currency_axis(ax, axis='x')
        else:
            bars = ax.bar(categories, values, color=bar_color)
            ax.set_xlabel(xlabel or "Category")
            ax.set_ylabel(ylabel or "Value")
            
            if len(categories) > 5 or any(len(str(c)) > 10 for c in categories):
                self.plt.xticks(rotation=45, ha='right')
            
            if show_values:
                self._add_data_labels(ax, bars, values, value_format)
            
            self._format_currency_axis(ax)
        
        ax.set_title(title, fontsize=self.config.typography.header_size,
                    fontweight='bold', pad=self.config.title_pad,
                    color=self.config.colors.accent)
        ax.grid(False)
        
        self.plt.tight_layout()
        return self._save_chart(fig, title, "bar")
    
    def line_chart(
        self,
        x_values: List[Any],
        y_values: List[float],
        title: str,
        xlabel: str = "",
        ylabel: str = "",
        color: str = None,
        show_markers: bool = True,
        fill_area: bool = False,
        comparison_line: Optional[Tuple[List[Any], List[float], str]] = None,
    ) -> ChartOutput:
        """Create a professional line chart."""
        fig, ax = self.plt.subplots(figsize=(10, 6))
        
        line_color = color or self.config.colors.primary
        marker = 'o' if show_markers else None
        
        ax.plot(x_values, y_values, color=line_color, marker=marker, 
               linewidth=2.5, markersize=6, label="Actual")
        
        if fill_area:
            ax.fill_between(x_values, y_values, alpha=0.2, color=line_color)
        
        if comparison_line:
            comp_x, comp_y, comp_label = comparison_line
            ax.plot(comp_x, comp_y, color=self.config.colors.secondary, 
                   linestyle='--', linewidth=2, label=comp_label)
            ax.legend(frameon=False)
        
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=self.config.typography.header_size,
                    fontweight='bold', pad=self.config.title_pad,
                    color=self.config.colors.accent)
        
        if len(x_values) > 6:
            self.plt.xticks(rotation=45, ha='right')
        
        self._format_currency_axis(ax)
        ax.grid(False)
        
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
        """Create a professional pie chart."""
        fig, ax = self.plt.subplots(figsize=(10, 8))
        
        # Use professional color palette
        if colors is None:
            colors = self.config.colors.series[:len(categories)]
        
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
                autotext.set_fontsize(self.config.typography.small_size)
                autotext.set_fontweight('bold')
        
        ax.set_title(title, fontsize=self.config.typography.header_size,
                    fontweight='bold', pad=self.config.title_pad,
                    color=self.config.colors.accent)
        
        self.plt.tight_layout()
        return self._save_chart(fig, title, "pie")
    
    # ==================== QUARTERLY TREND CHART (NEW) ====================
    
    def quarterly_trend_chart(
        self,
        quarters: List[str],
        values: List[float],
        title: str,
        ylabel: str = "Amount",
        show_yoy_change: bool = True,
        comparison_values: Optional[List[float]] = None,
        comparison_label: str = "Prior Year",
    ) -> ChartOutput:
        """
        Create a professional quarterly trend chart.
        
        Matches investment banking presentation standards.
        
        Args:
            quarters: List of quarter labels (e.g., ["Q1'23", "Q2'23", "Q3'23", "Q4'23"])
            values: Values for each quarter
            title: Chart title
            ylabel: Y-axis label
            show_yoy_change: Show year-over-year % change annotations
            comparison_values: Optional prior year values for comparison
            comparison_label: Label for comparison series
        
        Returns:
            ChartOutput with the generated chart
        """
        fig, ax = self.plt.subplots(figsize=(12, 6))
        
        x = range(len(quarters))
        bar_width = 0.35 if comparison_values else 0.6
        
        # Primary bars
        if comparison_values:
            bars1 = ax.bar(
                [i - bar_width/2 for i in x], 
                values, 
                bar_width, 
                label="Current",
                color=self.config.colors.primary,
            )
            bars2 = ax.bar(
                [i + bar_width/2 for i in x], 
                comparison_values, 
                bar_width, 
                label=comparison_label,
                color=self.config.colors.neutral,
                alpha=0.7,
            )
            ax.legend(loc='upper left', frameon=False)
        else:
            bars1 = ax.bar(x, values, bar_width, color=self.config.colors.primary)
        
        # Data labels on bars
        for bar, val in zip(bars1, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(values) * 0.01,
                f"${val/1e6:.1f}M" if val >= 1e6 else f"${val/1e3:.0f}K",
                ha='center',
                va='bottom',
                fontsize=self.config.typography.small_size,
                fontweight='bold',
            )
        
        # YoY change annotations
        if show_yoy_change and len(values) >= 5:
            for i in range(4, len(values)):
                prior_val = values[i - 4]  # Same quarter prior year
                if prior_val != 0:
                    yoy_change = (values[i] - prior_val) / abs(prior_val) * 100
                    color = self.config.colors.positive if yoy_change >= 0 else self.config.colors.negative
                    symbol = "+" if yoy_change >= 0 else ""
                    ax.annotate(
                        f"{symbol}{yoy_change:.1f}% YoY",
                        xy=(i, values[i] + max(values) * 0.08),
                        ha='center',
                        fontsize=8,
                        color=color,
                        fontweight='bold',
                    )
        
        # Styling
        ax.set_xlabel('')
        ax.set_ylabel(ylabel, fontsize=self.config.typography.body_size)
        ax.set_title(title, fontsize=self.config.typography.header_size, 
                    fontweight='bold', pad=self.config.title_pad,
                    color=self.config.colors.accent)
        ax.set_xticks(x)
        ax.set_xticklabels(quarters)
        
        # Remove gridlines for cleaner look
        ax.grid(False)
        ax.set_axisbelow(True)
        
        # Format y-axis
        self._format_currency_axis(ax)
        
        # Add subtle horizontal line at y=0 if there are negative values
        if min(values) < 0:
            ax.axhline(y=0, color=self.config.colors.neutral, linewidth=0.5)
        
        self.plt.tight_layout()
        return self._save_chart(fig, title, "quarterly_trend")
    
    # ==================== COMBO CHART (NEW) ====================
    
    def combo_chart(
        self,
        categories: List[str],
        bar_values: List[float],
        line_values: List[float],
        title: str,
        bar_label: str = "Amount",
        line_label: str = "Growth %",
        bar_ylabel: str = "Amount",
        line_ylabel: str = "Percentage",
    ) -> ChartOutput:
        """
        Create a combo chart with bars and line (common in financial presentations).
        
        Example: Revenue bars with growth rate line.
        """
        fig, ax1 = self.plt.subplots(figsize=(12, 6))
        
        x = range(len(categories))
        
        # Bar chart on primary axis
        bars = ax1.bar(x, bar_values, color=self.config.colors.primary, 
                      label=bar_label, alpha=0.8)
        ax1.set_xlabel('')
        ax1.set_ylabel(bar_ylabel, color=self.config.colors.primary)
        ax1.tick_params(axis='y', labelcolor=self.config.colors.primary)
        self._format_currency_axis(ax1)
        
        # Line chart on secondary axis
        ax2 = ax1.twinx()
        ax2.plot(x, line_values, color=self.config.colors.secondary, 
                marker='o', linewidth=2.5, markersize=8, label=line_label)
        ax2.set_ylabel(line_ylabel, color=self.config.colors.secondary)
        ax2.tick_params(axis='y', labelcolor=self.config.colors.secondary)
        ax2.yaxis.set_major_formatter(self.mticker.PercentFormatter(xmax=100))
        
        # Add % labels on line points
        for i, val in enumerate(line_values):
            ax2.annotate(
                f"{val:.1f}%",
                xy=(i, val),
                xytext=(0, 8),
                textcoords='offset points',
                ha='center',
                fontsize=9,
                fontweight='bold',
                color=self.config.colors.secondary,
            )
        
        ax1.set_xticks(x)
        ax1.set_xticklabels(categories)
        ax1.set_title(title, fontsize=self.config.typography.header_size,
                     fontweight='bold', pad=self.config.title_pad,
                     color=self.config.colors.accent)
        
        # Combined legend
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', frameon=False)
        
        ax1.grid(False)
        ax2.grid(False)
        
        self.plt.tight_layout()
        return self._save_chart(fig, title, "combo")
    
    def variance_chart(
        self,
        categories: List[str],
        actual: List[float],
        budget: List[float],
        title: str,
    ) -> ChartOutput:
        """Create a professional variance chart comparing actual vs budget."""
        fig, ax = self.plt.subplots(figsize=(12, 6))
        
        x = range(len(categories))
        width = 0.35
        
        bars1 = ax.bar([i - width/2 for i in x], actual, width, label='Actual', color=self.config.colors.primary)
        bars2 = ax.bar([i + width/2 for i in x], budget, width, label='Budget', color=self.config.colors.neutral, alpha=0.7)
        
        ax.set_xlabel('Category')
        ax.set_ylabel('Amount')
        ax.set_title(title, fontsize=self.config.typography.header_size,
                    fontweight='bold', pad=self.config.title_pad,
                    color=self.config.colors.accent)
        ax.set_xticks(x)
        ax.set_xticklabels(categories, rotation=45, ha='right')
        ax.legend(frameon=False)
        
        # Add variance annotations
        for i, (a, b) in enumerate(zip(actual, budget)):
            variance = a - b
            pct = (variance / b * 100) if b != 0 else 0
            color = self.config.colors.positive if variance >= 0 else self.config.colors.negative
            symbol = '+' if variance >= 0 else ''
            ax.annotate(
                f'{symbol}{pct:.1f}%',
                xy=(i, max(a, b) + max(actual) * 0.02),
                ha='center',
                fontsize=self.config.typography.small_size,
                color=color,
                fontweight='bold',
            )
        
        # Format y-axis
        self._format_currency_axis(ax)
        ax.grid(False)
        
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
        """Create a professional waterfall chart showing cumulative changes."""
        fig, ax = self.plt.subplots(figsize=(12, 6))
        
        # Calculate running total
        running_total = [0]
        for v in values:
            running_total.append(running_total[-1] + v)
        
        # Add start and end bars
        all_categories = [start_label] + categories + [end_label]
        
        # Colors for positive/negative using professional palette
        colors = [self.config.colors.neutral]  # Start bar
        for v in values:
            colors.append(self.config.colors.positive if v >= 0 else self.config.colors.negative)
        colors.append(self.config.colors.primary)  # End bar
        
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
                color=self.config.colors.neutral,
                linewidth=1,
            )
        
        # Add value labels
        for i, (cat, h, b) in enumerate(zip(all_categories, heights, bottoms)):
            val = h if i == 0 or i == len(all_categories) - 1 else (values[i-1] if i > 0 and i <= len(values) else h)
            ax.text(
                i, b + h + max(heights) * 0.02,
                f"${val:,.0f}",
                ha='center',
                fontsize=self.config.typography.small_size,
                fontweight='bold',
            )
        
        ax.set_ylabel('Amount')
        ax.set_title(title, fontsize=self.config.typography.header_size,
                    fontweight='bold', pad=self.config.title_pad,
                    color=self.config.colors.accent)
        self.plt.xticks(rotation=45, ha='right')
        
        self._format_currency_axis(ax)
        ax.grid(False)
        
        self.plt.tight_layout()
        return self._save_chart(fig, title, "waterfall")

# Factory function
def get_chart_generator(output_dir: str = ".charts", config: ChartConfig = None):
    """Get a chart generator instance, or None if matplotlib is not available."""
    try:
        return ChartGenerator(output_dir, config=config)
    except ImportError:
        logger.warning("Matplotlib not available - chart generation disabled")
        return None
