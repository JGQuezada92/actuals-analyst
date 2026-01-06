# PowerShell setup script for React client

Set-Location client

# Create Vite React TypeScript app if it doesn't exist
if (-not (Test-Path "package.json")) {
    Write-Host "Creating Vite React TypeScript app..."
    npm create vite@latest . -- --template react-ts
}

# Install dependencies
Write-Host "Installing dependencies..."
npm install

# Install UI dependencies
Write-Host "Installing UI dependencies..."
npm install @radix-ui/react-dialog @radix-ui/react-dropdown-menu `
  @radix-ui/react-scroll-area @radix-ui/react-separator `
  @radix-ui/react-slot @radix-ui/react-tabs @radix-ui/react-tooltip `
  @radix-ui/react-avatar @radix-ui/react-collapsible

# Install styling
npm install class-variance-authority clsx tailwind-merge tailwindcss-animate
npm install lucide-react recharts date-fns

# Install state & data
npm install zustand socket.io-client react-router-dom @tanstack/react-query

# Install notifications
npm install sonner

# Install dev dependencies
npm install -D tailwindcss postcss autoprefixer

# Initialize Tailwind
npx tailwindcss init -p

Write-Host "Client setup complete!"

Set-Location ..

