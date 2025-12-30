"""
Middleware to allow microphone access via Permissions-Policy header.
"""


class PermissionsPolicyMiddleware:
    """
    Add Permissions-Policy header to allow microphone access.
    This is required for getUserMedia API to work in browsers.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        # Allow microphone access for getUserMedia API
        # Try different header names for compatibility
        response['Permissions-Policy'] = 'microphone=*'
        response['Feature-Policy'] = 'microphone *'
        return response
