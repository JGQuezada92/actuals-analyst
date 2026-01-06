#!/bin/bash
# Setup script for React client

cd client || exit

# Create Vite React TypeScript app if it doesn't exist
if [ ! -f "package.json" ]; then
  echo "Creating Vite React TypeScript app..."
  npm create vite@latest . -- --template react-ts
fi

# Install dependencies
echo "Installing dependencies..."
npm install

# Install UI dependencies
echo "Installing UI dependencies..."
npm install @radix-ui/react-dialog @radix-ui/react-dropdown-menu \
  @radix-ui/react-scroll-area @radix-ui/react-separator \
  @radix-ui/react-slot @radix-ui/react-tabs @radix-ui/react-tooltip \
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

echo "Client setup complete!"

