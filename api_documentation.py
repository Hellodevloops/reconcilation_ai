"""
Step 13: API Documentation Generator

Generates OpenAPI/Swagger documentation for the reconciliation API.
"""

API_DOCS = {
    "openapi": "3.0.0",
    "info": {
        "title": "OCR Reconciliation API",
        "version": "1.0.0",
        "description": "API for OCR-based invoice and bank statement reconciliation"
    },
    "servers": [
        {
            "url": "http://localhost:5001",
            "description": "Local development server"
        }
    ],
    "paths": {
        "/api/health": {
            "get": {
                "summary": "Health check endpoint",
                "description": "Returns the health status of the API",
                "responses": {
                    "200": {
                        "description": "API is healthy",
                        "content": {
                            "application/json": {
                                "example": {
                                    "status": "healthy",
                                    "timestamp": "2024-01-15T10:30:00"
                                }
                            }
                        }
                    }
                }
            }
        },
        "/api/reconcile": {
            "post": {
                "summary": "Reconcile invoices with bank statements",
                "description": "Upload invoice and bank statement files (images, PDFs, Excel, CSV) and get reconciliation results",
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "invoice": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                            "format": "binary"
                                        },
                                        "description": "Invoice file(s) - images (PNG, JPG), PDF, Excel, or CSV"
                                    },
                                    "bank": {
                                        "type": "string",
                                        "format": "binary",
                                        "description": "Bank statement file - image (PNG, JPG), PDF, Excel, or CSV"
                                    }
                                },
                                "required": ["invoice", "bank"]
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Reconciliation successful",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "invoice_lines": {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        },
                                        "bank_lines": {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        },
                                        "reconciliation": {
                                            "type": "object",
                                            "properties": {
                                                "matches": {"type": "array"},
                                                "only_in_invoices": {"type": "array"},
                                                "only_in_bank": {"type": "array"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "400": {
                        "description": "Bad request - validation error"
                    },
                    "500": {
                        "description": "Internal server error"
                    }
                }
            }
        },
        "/api/reconciliations": {
            "get": {
                "summary": "List reconciliation history",
                "description": "Get a list of recent reconciliation runs",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {
                            "type": "integer",
                            "default": 50,
                            "maximum": 500
                        },
                        "description": "Maximum number of reconciliations to return"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "List of reconciliations",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "reconciliations": {
                                            "type": "array",
                                            "items": {"type": "object"}
                                        },
                                        "limit": {"type": "integer"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "/api/reconciliations/{reconciliation_id}/matches": {
            "get": {
                "summary": "Get matches for a reconciliation",
                "description": "Retrieve all matched pairs for a specific reconciliation",
                "parameters": [
                    {
                        "name": "reconciliation_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                        "description": "Reconciliation ID"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "List of matches",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"type": "object"}
                                }
                            }
                        }
                    },
                    "404": {
                        "description": "Reconciliation not found"
                    }
                }
            }
        },
        "/api/reconciliations/{reconciliation_id}/matches/export": {
            "get": {
                "summary": "Export matches as CSV",
                "description": "Export reconciliation matches to CSV format",
                "parameters": [
                    {
                        "name": "reconciliation_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"}
                    },
                    {
                        "name": "format",
                        "in": "query",
                        "schema": {
                            "type": "string",
                            "enum": ["csv", "excel"],
                            "default": "csv"
                        }
                    }
                ],
                "responses": {
                    "200": {
                        "description": "CSV file download"
                    }
                }
            }
        },
        "/api/reconciliations/{reconciliation_id}/matches/{match_id}": {
            "delete": {
                "summary": "Delete a match",
                "description": "Remove a matched pair from reconciliation",
                "parameters": [
                    {
                        "name": "reconciliation_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"}
                    },
                    {
                        "name": "match_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Match deleted successfully"
                    },
                    "404": {
                        "description": "Match not found"
                    }
                }
            }
        },
        "/api/reconciliations/{reconciliation_id}/manual-match": {
            "post": {
                "summary": "Create manual match",
                "description": "Manually create a match between invoice and bank transaction",
                "parameters": [
                    {
                        "name": "reconciliation_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"}
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "invoice": {
                                        "type": "object",
                                        "properties": {
                                            "description": {"type": "string"},
                                            "amount": {"type": "number"},
                                            "date": {"type": "string"}
                                        }
                                    },
                                    "bank": {
                                        "type": "object",
                                        "properties": {
                                            "description": {"type": "string"},
                                            "amount": {"type": "number"},
                                            "date": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Manual match created"
                    },
                    "400": {
                        "description": "Bad request"
                    }
                }
            }
        },
        "/api/process-document": {
            "post": {
                "summary": "Process a single document",
                "description": "Upload and process a single document (invoice or bank statement) for OCR",
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "file": {
                                        "type": "string",
                                        "format": "binary"
                                    }
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Document processed successfully"
                    }
                }
            }
        }
    }
}


def generate_openapi_json(output_path: str = None):
    """Generate OpenAPI JSON documentation."""
    import json
    
    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), "api_docs.json")
    
    with open(output_path, 'w') as f:
        json.dump(API_DOCS, f, indent=2)
    
    print(f"✓ OpenAPI documentation generated: {output_path}")
    return output_path


def generate_swagger_html(output_path: str = None):
    """Generate Swagger UI HTML page."""
    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), "static", "api_docs.html")
    
    html_template = """<!DOCTYPE html>
<html>
<head>
    <title>OCR Reconciliation API Documentation</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@4.15.5/swagger-ui.css" />
    <style>
        html { box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }
        *, *:before, *:after { box-sizing: inherit; }
        body { margin:0; background: #fafafa; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@4.15.5/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@4.15.5/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {
            const ui = SwaggerUIBundle({
                url: "/api/docs/json",
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                layout: "StandaloneLayout"
            });
        };
    </script>
</body>
</html>"""
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(html_template)
    
    print(f"✓ Swagger UI HTML generated: {output_path}")
    return output_path


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python api_documentation.py json   - Generate OpenAPI JSON")
        print("  python api_documentation.py html   - Generate Swagger UI HTML")
        print("  python api_documentation.py both   - Generate both")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "json":
        generate_openapi_json()
    elif command == "html":
        generate_swagger_html()
    elif command == "both":
        generate_openapi_json()
        generate_swagger_html()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


