# How to Clear Browser Cache - Complete Guide

## Quick Methods (Fastest)

### Method 1: Hard Refresh (Try This First!)
- **Windows/Linux**: Press `Ctrl + Shift + R` or `Ctrl + F5`
- **Mac**: Press `Cmd + Shift + R`
- This forces the browser to reload all files without using cache

### Method 2: Clear Cache for Current Site Only
- **Chrome/Edge**: 
  1. Press `F12` to open DevTools
  2. Right-click the refresh button (next to address bar)
  3. Select "Empty Cache and Hard Reload"

- **Firefox**:
  1. Press `F12` to open DevTools
  2. Right-click the refresh button
  3. Select "Empty Cache and Hard Reload"

---

## Complete Cache Clear (All Sites)

### Google Chrome
1. Press `Ctrl + Shift + Delete` (Windows) or `Cmd + Shift + Delete` (Mac)
2. Select "Cached images and files"
3. Time range: "All time" or "Last hour"
4. Click "Clear data"
5. **OR** go to: `chrome://settings/clearBrowserData`

### Microsoft Edge
1. Press `Ctrl + Shift + Delete`
2. Select "Cached images and files"
3. Time range: "All time"
4. Click "Clear now"
5. **OR** go to: `edge://settings/clearBrowserData`

### Mozilla Firefox
1. Press `Ctrl + Shift + Delete`
2. Select "Cache"
3. Time range: "Everything"
4. Click "Clear Now"
5. **OR** go to: `about:preferences#privacy` → Clear Data

### Safari (Mac)
1. Press `Cmd + Option + E` to clear cache
2. **OR** go to: Safari → Preferences → Advanced → Show Develop menu
3. Then: Develop → Empty Caches

---

## Developer Method (Most Reliable)

### Using DevTools
1. Open DevTools (`F12`)
2. Go to **Network** tab
3. Check **"Disable cache"** checkbox (at the top)
4. Keep DevTools open while testing
5. Refresh the page (`F5`)

This prevents the browser from using cache while DevTools is open.

---

## Nuclear Option (If Nothing Works)

### Clear Everything
1. Close all browser windows
2. Clear cache using methods above
3. Clear cookies for `localhost:5173`
4. Restart browser
5. Open in **Incognito/Private Window**:
   - Chrome/Edge: `Ctrl + Shift + N` (Windows) or `Cmd + Shift + N` (Mac)
   - Firefox: `Ctrl + Shift + P` (Windows) or `Cmd + Shift + P` (Mac)
6. Navigate to `http://localhost:5173`

---

## Verify CSS is Loading

After clearing cache:

1. Open `http://localhost:5173`
2. Press `F12` → **Network** tab
3. Refresh page (`F5`)
4. Look for CSS file:
   - Should see `index.css` or `index-[hash].css`
   - Status: **200 OK**
   - Size: **~6-7 KB**
   - Type: **text/css**

5. Click on the CSS file to see its contents
6. Should see Tailwind classes like `.bg-`, `.text-`, `.flex`, etc.

---

## If CSS Still Not Loading

Check these:

1. **Is the dev server running?**
   ```bash
   # Check if port 5173 is in use
   netstat -ano | findstr :5173
   ```

2. **Check browser console for errors:**
   - Press `F12` → **Console** tab
   - Look for red errors
   - Common issues:
     - 404 for CSS file
     - CORS errors
     - Network errors

3. **Try different browser:**
   - If Chrome doesn't work, try Edge or Firefox
   - This helps identify browser-specific issues

4. **Check if CSS file exists:**
   - In Network tab, click on the CSS file
   - Check "Response" tab
   - Should see actual CSS content, not HTML

---

## Still Not Working?

The issue might not be cache. Check:
- Dev server logs for errors
- Browser console for JavaScript errors
- Network tab for failed requests
- Verify `index.css` is imported in `main.tsx`

