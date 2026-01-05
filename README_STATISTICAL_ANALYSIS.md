# Statistical Analysis Module - Setup Guide

## Dependencies Installed ✅

All required packages are installed in the **64-bit Python 3.13** installation:
- ✅ numpy
- ✅ pandas  
- ✅ statsmodels
- ✅ arch
- ✅ scipy

## Using the Statistical Analysis Module

### Important: Use 64-bit Python

The system has both 32-bit and 64-bit Python 3.13 installed. The statistical packages are only available in the 64-bit version.

**To run analyses with statistical features, use:**

```bash
py -3.13 main.py analyze "your query here"
```

Instead of:
```bash
python main.py analyze "your query here"  # Uses 32-bit Python
```

### Making 64-bit Python Default (Optional)

If you want to make the 64-bit Python the default, you can:

1. **Update PATH** to prioritize the 64-bit Python location
2. **Create an alias** in PowerShell:
   ```powershell
   Set-Alias python "C:\Users\Jonathan Quezada\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
   ```

### Testing Statistical Analysis

Test the statistical analysis with:

```bash
py -3.13 main.py analyze "do a regression analysis by account to determine which most closely correlates with revenue. take into consideration seasonality and ARCH"
```

## Features Available

With the dependencies installed, you can now use:

1. **Correlation Analysis**: Correlate expense accounts with revenue
2. **Seasonality Decomposition**: Remove seasonal patterns from time series
3. **ARCH/GARCH Modeling**: Model volatility clustering in financial data
4. **Regression Analysis**: Statistical regression with significance testing
5. **Multi-lag Analysis**: Test correlations at different time lags

## Query Examples

- "Which expense accounts most closely correlate with revenue?"
- "Analyze revenue volatility using ARCH modeling"
- "Perform regression analysis by account, adjusting for seasonality"
- "What accounts drive revenue? Consider seasonality and ARCH effects"

