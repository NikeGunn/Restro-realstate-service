import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { X, Check } from 'lucide-react'

interface WidgetPreviewProps {
  widgetKey: string
  onClose: () => void
}

export function WidgetPreview({ widgetKey, onClose }: WidgetPreviewProps) {
  useEffect(() => {
    // Load widget script dynamically
    const script = document.createElement('script')
    script.src = 'http://localhost:8000/api/v1/widget/widget.js'
    script.setAttribute('data-widget-key', widgetKey)
    script.async = true
    document.body.appendChild(script)

    // Cleanup
    return () => {
      document.body.removeChild(script)
      // Remove widget elements
      const widgetContainer = document.getElementById('ai-chat-widget-container')
      if (widgetContainer) {
        widgetContainer.remove()
      }
    }
  }, [widgetKey])

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-background rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b">
          <div>
            <h2 className="text-xl font-bold">Widget Preview</h2>
            <p className="text-sm text-muted-foreground">
              Test your chatbot widget in real-time
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="p-6 bg-gradient-to-br from-blue-50 to-purple-50 dark:from-gray-900 dark:to-gray-800 min-h-[500px]">
          <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-8 max-w-2xl mx-auto">
            <h3 className="text-2xl font-bold mb-4">Demo Website</h3>
            <p className="text-muted-foreground mb-4">
              This is a preview of how your chatbot will appear on your website.
              The chat button should appear in the bottom-right corner.
            </p>
            <div className="bg-muted rounded p-4 mb-4">
              <p className="text-sm font-semibold mb-2">
                🎯 Try asking:
              </p>
              <ul className="text-sm text-muted-foreground ml-4 space-y-1">
                <li>• "What are your hours?"</li>
                <li>• "Do you have a menu?"</li>
                <li>• "Can I make a reservation?"</li>
                <li>• "What's your location?"</li>
              </ul>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" disabled>
                <Check className="h-4 w-4 mr-2" />
                Widget Active
              </Button>
              <Button variant="outline" onClick={onClose}>
                Close Preview
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
