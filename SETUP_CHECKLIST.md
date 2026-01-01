# ? COMPLETE SETUP CHECKLIST

## Quick Reference Checklist for Building Your Stock Dashboard

---

## ?? Pre-Setup Requirements

- [ ] Windows/macOS/Linux machine
- [ ] Python 3.10 or higher installed
- [ ] Git installed (already using it)
- [ ] Internet connection (for downloading packages)
- [ ] ~500MB free disk space
- [ ] Terminal/Command Prompt access

**Verify Python version:**
```bash
python --version
```
Should show: `Python 3.10.x` or higher

---

## ?? SETUP PROCESS (Choose One Method)

### METHOD 1: Automated Windows Setup (Recommended for Windows)

- [ ] Navigate to project directory
- [ ] Double-click `setup_windows.bat`
- [ ] Follow on-screen prompts
- [ ] Wait for completion message
- [ ] Terminal will stay open showing "Next Steps"

**Time**: ~3-5 minutes

---

### METHOD 2: Automated macOS/Linux Setup (Recommended for Mac/Linux)

```bash
# Step 1: Make script executable
chmod +x setup_macos_linux.sh

# Step 2: Run the script
./setup_macos_linux.sh

# Step 3: Wait for completion
```

**Time**: ~3-5 minutes

---

### METHOD 3: Manual Setup (All Platforms)

#### Step 1: Create Virtual Environment
```bash
python -m venv venv
```
- [ ] Command executed successfully
- [ ] `venv` folder appeared in project directory

#### Step 2: Activate Virtual Environment

**Windows (Command Prompt):**
```bash
venv\Scripts\activate
```

**Windows (PowerShell):**
```bash
.\venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

- [ ] Command prompt now shows `(venv)` at the beginning
- [ ] Verify with: `which python` (should show `venv/bin/python`)

#### Step 3: Upgrade pip
```bash
python -m pip install --upgrade pip
```
- [ ] pip upgraded successfully

#### Step 4: Install Dependencies
```bash
pip install -r requirements.txt
```
- [ ] Shows "Successfully installed" messages
- [ ] No error messages
- [ ] Progress bar completed

#### Step 5: Verify Installation
```bash
python test_setup.py
```
- [ ] All 9 tests show ? PASSED
- [ ] Final message: "All checks passed! Your environment is ready."

#### Step 6: Start Dashboard
```bash
python run_dashboard_interactive_host.py
```
- [ ] Shows Dash running message
- [ ] Shows URL: `http://127.0.0.1:8050`
- [ ] No error messages

---

## ?? Configuration (Optional but Recommended)

### Create .env File

- [ ] Create new file: `.env` in project root
- [ ] Add this line:
```
NEWS_API_KEY=your_free_key_here
```
- [ ] Get key from: https://newsapi.org (free signup)
- [ ] Save file

---

## ?? Verification Steps

### Quick Verification
```bash
python test_setup.py
```
Expected output:
```
? Python Version               PASSED
? Requirements                 PASSED
? Project Structure            PASSED
? Indicator Imports            PASSED
? News/Sentiment Imports       PASSED
? Signal Generator Imports     PASSED
? Basic Functionality          PASSED
? Environment Variables        PASSED
? Venv Instructions            PASSED

Total: 9/9 tests passed
? All checks passed! Your environment is ready.
```

- [ ] All 9 tests pass

### Test Individual Components
```bash
# Test indicators
python -c "from src.indicators import RSI; print('? Indicators OK')"

# Test signal generator
python -c "from modules.signal_generator import SignalGenerator; print('? Signals OK')"

# Test sentiment analyzer
python -c "from modules.news_sentiment_analyzer import SentimentAnalyzer; print('? Sentiment OK')"
```

- [ ] All three commands show success messages

---

## ?? Running the Dashboard

### Start Dashboard
```bash
python run_dashboard_interactive_host.py
```

- [ ] Terminal shows: "Running on http://127.0.0.1:8050"
- [ ] No error messages
- [ ] Press Ctrl+C to stop when done

### Access Dashboard
- [ ] Open browser
- [ ] Go to: `http://127.0.0.1:8050`
- [ ] Dashboard loads successfully
- [ ] Can see stock charts and indicators

---

## ?? Features to Test

Once dashboard is running:

- [ ] Stock symbols load correctly
- [ ] Price charts display
- [ ] Technical indicators calculate
- [ ] Buy/Sell signals appear
- [ ] News feed loads (if API key configured)
- [ ] Sentiment indicators show
- [ ] No console errors

---

## ?? Troubleshooting Checklist

### Problem: "Python not found"
- [ ] Run: `python --version`
- [ ] If error: Install Python from python.org
- [ ] Ensure "Add Python to PATH" is checked during install

### Problem: "venv fails to create"
- [ ] Try: `python -m venv venv --upgrade-deps`
- [ ] Or: Delete `venv` folder and retry
- [ ] Ensure sufficient disk space

### Problem: "Permission denied" (macOS/Linux)
- [ ] Run: `chmod +x setup_macos_linux.sh`
- [ ] Then: `./setup_macos_linux.sh`

### Problem: "Port 8050 already in use"
- [ ] Kill process on port 8050
- **Windows**: `netstat -ano | findstr :8050`
- **macOS/Linux**: `lsof -i :8050`
- [ ] Or use different port: `python run_dashboard_interactive_host.py --port 8051`

### Problem: "Module not found" errors
- [ ] Verify venv is activated (shows `(venv)` in prompt)
- [ ] Reinstall: `pip install -r requirements.txt`
- [ ] Try: `pip install -r requirements.txt --force-reinstall`

### Problem: "NewsAPI not working"
- [ ] Create `.env` file with key
- [ ] Get key from: https://newsapi.org
- [ ] Check key is correct (no spaces)
- [ ] Test: `curl https://newsapi.org/v2/everything?q=AAPL&apiKey=YOUR_KEY`

### Problem: "Tests failing"
- [ ] Make sure all requirements installed: `pip install -r requirements.txt`
- [ ] Check Python version: `python --version` (need 3.10+)
- [ ] Run: `python test_setup.py` for detailed diagnostics

---

## ?? Project Files Verification

After setup, verify these files exist:

- [ ] `src/indicators/__init__.py` - Main indicators
- [ ] `src/indicators/advanced_indicators.py` - Re-exports
- [ ] `modules/signal_generator.py` - Trading signals
- [ ] `modules/news_sentiment_analyzer.py` - News & sentiment
- [ ] `modules/advanced_indicators.py` - Legacy indicators
- [ ] `tests/test_advanced_indicators.py` - Tests
- [ ] `requirements.txt` - Dependencies
- [ ] `environment.yml` - Conda config
- [ ] `test_setup.py` - Verification script
- [ ] `setup_windows.bat` - Windows automation
- [ ] `setup_macos_linux.sh` - Unix automation
- [ ] `run_dashboard_interactive_host.py` - Main app

---

## ?? Documentation Files

Review these for more info:

- [ ] `README_BUILD_GUIDE.md` - Complete setup guide
- [ ] `SETUP_GUIDE.md` - Detailed configuration
- [ ] `CHANGES_VERIFICATION.md` - What was changed
- [ ] Docstrings in Python files

---

## ?? Security Checklist

- [ ] `.env` file created with NEWS_API_KEY
- [ ] `.env` file added to `.gitignore` (if using git)
- [ ] No API keys in code or commits
- [ ] Virtual environment isolated from system
- [ ] Dependencies verified from requirements.txt

---

## ? Final Verification

- [ ] Virtual environment created
- [ ] Virtual environment activated
- [ ] All dependencies installed
- [ ] `python test_setup.py` returns 9/9 passed
- [ ] Dashboard starts without errors
- [ ] Dashboard accessible at `http://127.0.0.1:8050`
- [ ] All features working (indicators, news, sentiment, signals)

---

## ?? Next: Using the Dashboard

Once everything is set up:

1. [ ] Add your favorite stock symbols
2. [ ] Monitor technical indicators
3. [ ] Review buy/sell signals
4. [ ] Check news and sentiment
5. [ ] Make informed trading decisions

---

## ?? Quick Reference Commands

Save these commands:

```bash
# Activate virtual environment
venv\Scripts\activate              # Windows
source venv/bin/activate           # macOS/Linux

# Run verification
python test_setup.py

# Start dashboard
python run_dashboard_interactive_host.py

# Run tests
python -m pytest tests/ -v

# Deactivate venv when done
deactivate

# Update dependencies
pip install -r requirements.txt --upgrade

# Check installed packages
pip list
```

---

## ?? Setup Completion Checklist

### Before Setup
- [ ] Python 3.10+ installed
- [ ] Project directory available
- [ ] Internet connection available

### During Setup
- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] Configuration files created
- [ ] Tests passing

### After Setup
- [ ] Dashboard runs without errors
- [ ] Can access `http://127.0.0.1:8050`
- [ ] All features accessible
- [ ] Ready to use

---

## ?? Ready to Build!

**Checklist Status**: Complete ?

You're all set to:
1. Create your virtual environment
2. Install dependencies
3. Run your dashboard
4. Start analyzing stocks!

---

## ?? Support Reference

| Issue | Solution |
|-------|----------|
| Python not found | Install from python.org |
| venv fails | Try `python -m venv venv --upgrade-deps` |
| Import errors | Ensure venv is activated |
| Port in use | Use `--port 8051` flag |
| Tests failing | Run `python test_setup.py` for details |
| News not working | Add NEWS_API_KEY to .env |

---

**Last Updated**: 2026-01-01  
**Status**: Ready to Build  
**Version**: 1.0  

**Good luck! Happy analyzing! ??**
