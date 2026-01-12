"""
Production Deployment Guide for Multi-Invoice Support
Comprehensive setup and configuration instructions
"""

# Multi-Invoice Support - Production Deployment Guide

## Overview

This guide provides comprehensive instructions for deploying the enhanced multi-invoice processing system in a production environment. The system now supports processing files containing multiple invoices while maintaining a single primary record per file upload.

## Architecture

### New Data Model
- **file_uploads**: Parent records for uploaded files (single primary key per file)
- **extracted_invoices**: Individual invoices extracted from files (child records)
- **invoice_line_items**: Line items within each invoice
- **processing_jobs**: Background job tracking for async processing

### Key Features
- Single primary key per file upload
- Asynchronous processing of large files
- Support for PDF, Excel, and image files
- AI-based invoice extraction with confidence scoring
- Scalable database design with proper indexing
- Production-ready error handling and logging

## Prerequisites

### System Requirements
- Python 3.8+
- SQLite 3.35+ (for production, consider PostgreSQL)
- Minimum 4GB RAM
- 50GB+ storage (depending on file volume)
- Redis (for background job processing, optional)

### Python Dependencies
```bash
pip install flask flask-limiter
pip install PyPDF2 pytesseract pillow pandas
pip install python-dotenv joblib
pip install celery redis  # Optional for advanced background processing
```

### External Dependencies
- Tesseract OCR engine
- ImageMagick (for image processing)
- Sufficient disk space for file storage

## Installation Steps

### 1. Database Migration
```bash
cd /path/to/your/project
python migrations/add_multi_invoice_support.py
```

### 2. Update Application Configuration
Add to your main app.py:
```python
from integration.multi_invoice_integration import integrate_multi_invoice_support

# After creating your Flask app:
app = Flask(__name__)
app = integrate_multi_invoice_support(app)
```

### 3. Configure File Storage
Ensure proper permissions and storage:
```python
# In config.py or environment variables
UPLOAD_FOLDER = '/var/www/invoice_uploads'
INVOICE_FOLDER = '/var/www/invoice_uploads/invoices'
MAX_FILE_SIZE_MB = 100  # Adjust based on your needs
MAX_TOTAL_SIZE_MB = 500  # Adjust based on your needs
```

### 4. Set Up Background Processing
For production, use Celery with Redis:
```python
# celery_app.py
from celery import Celery
from services.multi_invoice_processor import multi_invoice_processor

celery = Celery('invoice_processor', broker='redis://localhost:6379/0')

@celery.task
def process_file_background(file_upload_id):
    return multi_invoice_processor.process_file_async(file_upload_id)
```

## API Endpoints

### New Endpoints
- `POST /api/upload-invoice-file` - Upload files with multiple invoices
- `GET /api/upload-status/<job_id>` - Check processing status
- `GET /api/file-uploads` - List all file uploads
- `GET /api/file-uploads/<id>` - Get detailed file upload info
- `GET /api/file-uploads/<id>/invoices` - Get invoices from a file
- `GET /api/file-uploads/<id>/download` - Download original file
- `DELETE /api/file-uploads/<id>` - Delete file upload

### Usage Examples

#### Upload a File
```bash
curl -X POST http://localhost:5001/api/upload-invoice-file \
  -F "file=@multi_invoice.pdf" \
  -F "description=Batch of invoices from January"
```

Response:
```json
{
  "success": true,
  "file_upload_id": 123,
  "job_id": "abc-123-def",
  "file_name": "multi_invoice.pdf",
  "processing_status": "pending"
}
```

#### Check Processing Status
```bash
curl http://localhost:5001/api/upload-status/abc-123-def
```

Response:
```json
{
  "job_id": "abc-123-def",
  "status": "completed",
  "progress": 1.0,
  "file_upload": {
    "total_invoices_found": 15,
    "total_invoices_processed": 15,
    "total_amount": 15420.50,
    "extraction_confidence": 0.87
  }
}
```

## Production Configuration

### Environment Variables
```bash
# Database
DATABASE_PATH=/var/lib/invoice_processor/reconcile.db

# File Storage
UPLOAD_FOLDER=/var/www/invoice_uploads
MAX_FILE_SIZE_MB=100
MAX_TOTAL_SIZE_MB=500

# Rate Limiting
RATE_LIMIT=100 per minute
RATE_LIMIT_UPLOAD=20 per minute

# Background Processing
ENABLE_CACHING=1
CACHE_TTL_SECONDS=300

# Security
ALLOWED_ORIGINS=https://yourdomain.com
CORS_ENABLED=1
```

### Nginx Configuration
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    client_max_body_size 500M;
    
    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
    
    location /static {
        alias /var/www/invoice_processor/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### Systemd Service
```ini
# /etc/systemd/system/invoice-processor.service
[Unit]
Description=Invoice Processing Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/invoice_processor
Environment=PATH=/var/www/invoice_processor/venv/bin
ExecStart=/var/www/invoice_processor/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Monitoring and Logging

### Application Logging
The system uses structured logging with the following levels:
- INFO: Normal operations
- WARNING: Non-critical issues
- ERROR: Processing failures
- CRITICAL: System failures

### Key Metrics to Monitor
- File upload success rate
- Processing time per file
- Invoice extraction confidence scores
- Database query performance
- Disk space usage
- Memory usage during processing

### Health Check Endpoint
```bash
curl http://localhost:5001/api/health
```

## Performance Optimization

### Database Optimization
1. Use appropriate indexes (already included in migration)
2. Consider PostgreSQL for high-volume deployments
3. Implement connection pooling
4. Regular database maintenance

### File Processing Optimization
1. Implement file size limits
2. Use background processing for large files
3. Cache frequently accessed data
4. Optimize OCR settings for your document types

### Scaling Considerations
1. Horizontal scaling with multiple app instances
2. Load balancer configuration
3. Distributed file storage (S3, etc.)
4. Redis cluster for background jobs

## Security Considerations

### File Upload Security
- File type validation
- File size limits
- Virus scanning integration
- Secure file storage

### API Security
- Rate limiting
- Input validation
- CORS configuration
- Authentication/authorization

### Data Protection
- Encrypt sensitive data
- Regular backups
- Access controls
- Audit logging

## Backup and Recovery

### Database Backup
```bash
# SQLite backup
sqlite3 /path/to/reconcile.db ".backup backup_$(date +%Y%m%d).db"

# Automated backup script
#!/bin/bash
BACKUP_DIR="/var/backups/invoice_processor"
DATE=$(date +%Y%m%d_%H%M%S)
sqlite3 $DATABASE_PATH ".backup $BACKUP_DIR/reconcile_$DATE.db"
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
```

### File Backup
```bash
# Sync to backup location
rsync -av /var/www/invoice_uploads/ /backup/invoice_uploads/
```

## Troubleshooting

### Common Issues

#### Migration Fails
- Check database permissions
- Ensure no other processes are using the database
- Verify SQLite version compatibility

#### File Processing Fails
- Check Tesseract installation
- Verify file permissions
- Monitor memory usage
- Check OCR logs

#### Performance Issues
- Monitor database query times
- Check disk I/O
- Review background job queue
- Analyze memory usage patterns

### Debug Mode
Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Testing

### Unit Tests
```bash
python -m pytest tests/test_multi_invoice.py -v
```

### Integration Tests
```bash
python tests/test_multi_invoice.py
```

### Load Testing
Use tools like Apache Bench or Locust:
```bash
ab -n 100 -c 10 http://localhost:5001/api/health
```

## Migration from Old System

### Data Migration
The system includes a migration endpoint:
```bash
curl -X POST http://localhost:5001/api/migrate-existing-data
```

### Backward Compatibility
- Existing API endpoints continue to work
- Old data is automatically linked to new structure
- Gradual migration approach recommended

## Support and Maintenance

### Regular Maintenance Tasks
1. Monitor disk space usage
2. Review processing logs
3. Update OCR models
4. Performance tuning
5. Security updates

### Support Contact
- Check application logs for errors
- Monitor system health endpoints
- Review performance metrics regularly

---

## Quick Start Checklist

- [ ] Run database migration
- [ ] Update application configuration
- [ ] Set up file storage directories
- [ ] Configure background processing
- [ ] Set up monitoring and logging
- [ ] Test with sample files
- [ ] Configure backup procedures
- [ ] Set up production monitoring
- [ ] Document your specific configuration
- [ ] Train support team

This system is now production-ready with enterprise-level features for handling multi-invoice files efficiently and reliably.
