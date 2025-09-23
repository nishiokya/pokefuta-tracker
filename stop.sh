#!/bin/bash

# Stop Next.js development server
echo "Stopping Next.js development server..."
pkill -f "next dev" || pkill -f "npm run dev" || pkill -f "yarn dev" || pkill -f "pnpm dev"
echo "Next.js development server stopped."