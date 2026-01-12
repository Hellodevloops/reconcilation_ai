"""
Celery tasks for OCR processing
Enables async/background OCR processing
"""

from celery_app import celery_app
import base64
import io
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name='tasks.process_ocr')
def process_ocr_task(self, file_data: str, file_type: str, file_name: str, source: str) -> Dict[str, Any]:
    """
    Process OCR on a file asynchronously
    
    Args:
        file_data: Base64 encoded file data
        file_type: Type of file (image, pdf, excel, csv)
        file_name: Name of the file
        source: Source type (invoice or bank)
    
    Returns:
        Dictionary with OCR results
    """
    try:
        # Update task state
        self.update_state(state='PROCESSING', meta={'progress': 10, 'message': 'Starting OCR...'})
        
        # Decode file data
        file_bytes = base64.b64decode(file_data)
        
        # Import OCR functions from app (or refactored service)
        # For now, this is a placeholder - integrate with actual OCR code
        self.update_state(state='PROCESSING', meta={'progress': 50, 'message': 'Processing OCR...'})
        
        # TODO: Integrate with actual OCR processing
        # from services.ocr_service import process_ocr
        # result = process_ocr(file_bytes, file_type, source)
        
        self.update_state(state='PROCESSING', meta={'progress': 90, 'message': 'Finalizing...'})
        
        # Placeholder result
        result = {
            'status': 'success',
            'file_name': file_name,
            'source': source,
            'transactions': [],
            'raw_lines': []
        }
        
        return result
    except Exception as e:
        logger.error(f"OCR task failed: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


@celery_app.task(bind=True, name='tasks.process_multiple_ocr')
def process_multiple_ocr_task(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process multiple files in parallel
    
    Args:
        files: List of file dictionaries with file_data, file_type, file_name, source
    
    Returns:
        List of OCR results
    """
    try:
        total_files = len(files)
        results = []
        
        for idx, file_info in enumerate(files):
            progress = int((idx / total_files) * 100)
            self.update_state(
                state='PROCESSING',
                meta={
                    'progress': progress,
                    'message': f'Processing file {idx + 1} of {total_files}',
                    'current_file': file_info.get('file_name', 'unknown')
                }
            )
            
            # Process each file
            result = process_ocr_task.apply_async(args=[
                file_info['file_data'],
                file_info['file_type'],
                file_info['file_name'],
                file_info['source']
            ]).get()
            
            results.append(result)
        
        return results
    except Exception as e:
        logger.error(f"Multiple OCR task failed: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise

