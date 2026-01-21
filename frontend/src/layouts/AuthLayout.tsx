import { Outlet, Link } from 'react-router-dom'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { MessageSquare, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function AuthLayout() {
  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Navbar */}
      <nav className="bg-white/80 backdrop-blur-sm border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-xl flex items-center justify-center">
                <MessageSquare className="h-6 w-6 text-white" />
              </div>
              <span className="text-xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                Kribaat
              </span>
            </Link>

            {/* Right side */}
            <div className="flex items-center gap-4">
              <LanguageSwitcher variant="compact" />
              <Link to="/">
                <Button variant="ghost" size="sm" className="gap-2">
                  <ArrowLeft className="h-4 w-4" />
                  Back to Home
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <Outlet />
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-white/80 backdrop-blur-sm border-t border-gray-200 py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-sm text-gray-600">
              © {new Date().getFullYear()} Kribaat. All rights reserved.
            </p>
            <div className="flex items-center gap-6 text-sm text-gray-600">
              <span className="flex items-center gap-2 cursor-not-allowed">
                Privacy Policy
                <span className="text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded">Soon</span>
              </span>
              <span className="flex items-center gap-2 cursor-not-allowed">
                Terms of Service
                <span className="text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded">Soon</span>
              </span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
