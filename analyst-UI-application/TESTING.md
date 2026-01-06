# Testing the UI Application

## Quick Test Steps

### 1. Verify Servers Are Running

**Check Backend:**
```bash
curl http://localhost:3001/health
```

Should return:
```json
{
  "status": "ok",
  "timestamp": "...",
  "services": {
    "traceStore": true,
    "agentBridge": true
  }
}
```

**Check Frontend:**
- Open http://localhost:5173 in your browser
- You should see the Financial Analyst UI with sidebar navigation

### 2. Test Chat Interface

1. Navigate to **Chat** tab (default)
2. Type a query: `What are our total expenses YTD?`
3. Press Enter or click Send button
4. You should see:
   - Your message appear immediately
   - Typing indicator
   - Progress updates (Phase 1, Phase 2, etc.)
   - Final analysis response

### 3. Test Trace Viewer

1. Navigate to **Traces** tab
2. You should see a list of traces (if any exist)
3. Each trace shows:
   - Query text
   - Status (ok/error)
   - Duration
   - Cost
   - Token count
   - Timestamp

### 4. Test Admin Dashboard

1. Navigate to **Admin** tab
2. You should see metrics:
   - Total Traces
   - Success Rate
   - Total Cost
   - Average Duration

### 5. Test Theme Toggle

1. Click the sun/moon icon in the header
2. UI should switch between light and dark themes
3. Preference is saved in localStorage

## Expected Behavior

### Chat Flow

1. **Send Message** → User message appears immediately
2. **Server Processing** → Typing indicator shows
3. **Progress Updates** → Phase messages appear (e.g., "Phase 1: Data Retrieval")
4. **Response** → Analysis appears with:
   - Formatted text
   - Calculations (if any)
   - Metadata (trace ID, evaluation score)

### Error Handling

- If Python agent fails → Error message displayed
- If WebSocket disconnects → "Connecting..." message
- If server unavailable → Connection error shown

## Troubleshooting

### Server Not Starting

**Check logs:**
```bash
# Look for errors in terminal output
# Common issues:
# - Port 3001 already in use
# - Python path incorrect
# - main.py not found
```

**Fix Python path:**
Edit `.env`:
```env
PYTHON_PATH=py -3.13
# or
PYTHON_PATH=C:\Python313\python.exe
```

### Client Not Loading

**Check browser console:**
- Open DevTools (F12)
- Look for errors in Console tab
- Check Network tab for failed requests

**Common issues:**
- CORS errors → Check `CORS_ORIGIN` in `.env`
- Socket connection failed → Verify server is running
- 404 errors → Check Vite proxy configuration

### No Traces Showing

**Check traces directory:**
```bash
# Traces should be in parent directory
ls ../traces/
```

**Generate a trace:**
- Send a query through the chat
- A trace file should be created automatically
- Refresh the Traces tab

## Test Queries

Try these queries to test different features:

1. **Basic Total:**
   ```
   What are our total expenses YTD?
   ```

2. **Department Filter:**
   ```
   Show me Finance department expenses
   ```

3. **Trend Analysis:**
   ```
   What is the quarterly trend of expenses?
   ```

4. **Statistical:**
   ```
   Do a regression analysis by account to determine which most closely correlates with revenue
   ```

## Success Criteria

✅ Chat interface loads and displays messages
✅ Messages send via WebSocket
✅ Progress updates appear in real-time
✅ Analysis responses display correctly
✅ Traces tab shows trace list
✅ Admin dashboard displays metrics
✅ Theme toggle works
✅ Navigation between tabs works
✅ Error messages display appropriately

## Next Steps After Testing

1. **Customize UI** - Modify colors, fonts, layout
2. **Add Features** - Chart visualization, export functionality
3. **Enhance Trace Viewer** - Add span tree, timeline view
4. **Improve Admin** - Add more metrics, charts
5. **Production Deploy** - Build and deploy to production

---

**Happy Testing!** 🚀

