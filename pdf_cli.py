"""
How to use :
    python pdf_cli.py summarize invoice.pdf --mode brief --backend openai
    python pdf_cli.py summarize contract.pdf --mode detailed --backend hf
    python pdf_cli.py status job_abc123
    python pdf_cli.py list-jobs
"""

import click
import requests
import time
import json
from pathlib import Path
from typing import Optional


API_BASE_URL = "http://localhost:8000/api"
TIMEOUT = 60 


class Colors:
   #terminal colors
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def print_header(text):
    
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}  {text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}\n")


def print_success(text):
    print(f"{Colors.GREEN} {text}{Colors.END}")


def print_error(text):
    print(f"{Colors.RED} {text}{Colors.END}")


def print_info(text):
    print(f"{Colors.BLUE} {text}{Colors.END}")


def print_warning(text):
    print(f"{Colors.YELLOW} {text}{Colors.END}")


def check_server():
    #Check if api server is running
    try:
        response = requests.get(f"{API_BASE_URL.replace('/api', '')}/health", timeout=2)
        return response.status_code == 200
    except requests.ConnectionError:
        return False


def wait_for_completion(job_id: str, max_wait: int = 60) -> Optional[dict]:
    # status polling until completion or timeout
    print(f"\n{Colors.YELLOW} Processing{Colors.END}")
    
    start_time = time.time()
    last_progress = -1
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(f"{API_BASE_URL}/status/{job_id}")
            
            if response.status_code != 200:
                print_error(f"Status check failed: {response.status_code}")
                return None
            
            data = response.json()
            status = data['status']
            progress = data.get('progress', 0)
            message = data.get('message', '')
            
            # Show progress bar
            if progress != last_progress:
                bar_length = 30
                filled = int(bar_length * progress / 100)
                bar = '*' * filled + '' * (bar_length - filled)
                print(f"\r{Colors.BLUE}[{bar}] {progress}%{Colors.END} - {message}", end='', flush=True)
                last_progress = progress
            
            if status == 'completed':
                print()
                print_success(f"Completed in {time.time() - start_time:.2f}s")
                return data
            elif status == 'failed':
                print()
                print_error(f"Processing failed: {data.get('error_message', 'Unknown error')}")
                return None
            
            time.sleep(0.5)  # poll every 0.5 seconds
            
        except Exception as e:
            print_error(f"Error polling status: {e}")
            return None
    
    print()
    print_warning(f"Timeout after {max_wait}s")
    return None


@click.group()
def cli():
    pass


@cli.command()
@click.argument('pdf_file', type=click.Path(exists=True))
@click.option('--mode', '-m', 
              type=click.Choice(['brief', 'detailed', 'bullets'], case_sensitive=False),
              default='brief',
              help='Summary mode')
@click.option('--backend', '-b',
              type=click.Choice(['openai', 'hf'], case_sensitive=False),
              default='openai',
              help='LLM backend to use')
@click.option('--max-pages', '-p',
              type=int,
              default=3,
              help='Maximum pages to process (1-3)')
@click.option('--entities/--no-entities',
              default=True,
              help='Extract entities from document')
@click.option('--output', '-o',
              type=click.Path(),
              default=None,
              help='Save output to JSON file')
@click.option('--sync',
              is_flag=True,
              help='Use synchronous endpoint (blocks until done)')
def summarize(pdf_file, mode, backend, max_pages, entities, output, sync):
    print_header(f"pdf SUMMARIZER - {mode.upper()} MODE")
    
    # Check server
    if not check_server():
        print_error("api server is not running!")
        print_info("Start the server with: uvicorn app.main:app --reload")
        return
    
    pdf_path = Path(pdf_file)
    print_info(f"File: {pdf_path.name} ({pdf_path.stat().st_size / 1024:.1f} KB)")
    print_info(f"Mode: {mode}")
    print_info(f"Backend: {backend.upper()}")
    print_info(f"Max pages: {max_pages}")
    
    # Use sync endpoint if requested
    if sync:
        print_info("Using synchronous processing...")
        
        try:
            with open(pdf_path, 'rb') as f:
                files = {'file': (pdf_path.name, f, 'application/pdf')}
                data = {
                    'summary_mode': mode,
                    'llm_backend': backend,
                    'max_pages': max_pages
                }
                
                print(f"\n{Colors.YELLOW} Processing {Colors.END}")
                response = requests.post(
                    f"{API_BASE_URL}/summarize-sync",
                    files=files,
                    data=data,
                    timeout=30
                )
            
            if response.status_code != 200:
                print_error(f"Processing failed: {response.status_code}")
                print_error(response.text)
                return
            
            result = response.json()
            display_results(result, output)
            
        except Exception as e:
            print_error(f"Error: {e}")
            return
    
    # Use async workflow -> upload > process > wait
    else:
        try:
            # Upload
            print(f"\n{Colors.YELLOW} Uploading pdf {Colors.END}")
            
            with open(pdf_path, 'rb') as f:
                files = {'file': (pdf_path.name, f, 'application/pdf')}
                params = {
                    'max_pages': max_pages,
                    'extract_tables': True
                }
                response = requests.post(f"{API_BASE_URL}/upload", files=files, params=params)
            
            if response.status_code != 200:
                print_error(f"Upload failed: {response.status_code}")
                print_error(response.text)
                return
            
            upload_data = response.json()
            job_id = upload_data['job_id']
            print_success(f"Uploaded! Job ID: {job_id}")
            
            # Step 2: Process
            print(f"\n{Colors.YELLOW} Starting processing {Colors.END}")
            
            process_data = {
                'job_id': job_id,
                'summary_mode': mode,
                'llm_backend': backend,
                'extract_entities': entities,
                'entity_types': ['date', 'money', 'person', 'organization', 'location'] if entities else None
            }
            
            response = requests.post(f"{API_BASE_URL}/process", json=process_data)
            
            if response.status_code != 200:
                print_error(f"Process request failed: {response.status_code}")
                print_error(response.text)
                return
            
            print_success("Processing started in background")
            
            # Step 3: Wait for completion
            result = wait_for_completion(job_id, max_wait=TIMEOUT)
            
            if result and result['status'] == 'completed':
                display_results(result['result'], output)
            elif result and result['status'] == 'failed':
                print_error(f"Processing failed: {result.get('error_message', 'Unknown error')}")
            
        except Exception as e:
            print_error(f"Error: {e}")
            return


def display_results(result: dict, output_file: Optional[str] = None):
    
    print_header("SUMMARY")
    print(result['summary'])
    
    if 'entities' in result and result['entities']:
        print_header(f"ENTITIES ({result['metadata']['entity_count']} found)")
        
        # Group by type
        by_type = {}
        for entity in result['entities']:
            entity_type = entity['type']
            if entity_type not in by_type:
                by_type[entity_type] = []
            by_type[entity_type].append(entity)
        
        for entity_type, entities in sorted(by_type.items()):
            print(f"\n{Colors.BOLD}{entity_type.upper()}:{Colors.END}")
            for entity in entities[:10]:  # Show first 10
                confidence = f"{entity['confidence']:.0%}" if 'confidence' in entity else ""
                print(f"  • {entity['text']} {Colors.YELLOW}{confidence}{Colors.END}")
            
            if len(entities) > 10:
                print(f"  {Colors.YELLOW}... and {len(entities) - 10} more{Colors.END}")
    
    print_header("METADATA")
    metadata = result['metadata']
    print(f"  Model: {Colors.BOLD}{metadata.get('model', metadata.get('model_used', 'unknown'))}{Colors.END}")
    print(f"  Backend: {metadata.get('backend', 'unknown')}")
    print(f"  Processing time: {metadata.get('processing_time_seconds', 0):.2f}s")
    print(f"  Pages processed: {metadata.get('pages_processed', 0)}")
    print(f"  Text length: {metadata.get('text_length', 0)} chars")
    
    # Save to file if requested
    if output_file:
        output_path = Path(output_file)
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n{Colors.GREEN} Saved to: {output_path}{Colors.END}")


@cli.command()
@click.argument('job_id')
@click.option('--output', '-o',
              type=click.Path(),
              default=None,
              help='Save output to JSON file')
def status(job_id, output):
    print_header(f"JOB STATUS: {job_id}")
    
    if not check_server():
        print_error("API server is not running!")
        return
    
    try:
        response = requests.get(f"{API_BASE_URL}/status/{job_id}")
        
        if response.status_code == 404:
            print_error("Job not found!")
            return
        
        if response.status_code != 200:
            print_error(f"Error: {response.status_code}")
            return
        
        data = response.json()
        
        print(f"Status: {Colors.BOLD}{data['status'].upper()}{Colors.END}")
        print(f"Progress: {data['progress']}%")
        print(f"Message: {data.get('message', 'N/A')}")
        print(f"Created: {data['created_at']}")
        print(f"Updated: {data['updated_at']}")
        
        if data.get('error_message'):
            print(f"Error: {Colors.RED}{data['error_message']}{Colors.END}")
        
        if data.get('result'):
            print_success("\nJob completed! Results available.")
            display_results(data['result'], output)
        
    except Exception as e:
        print_error(f"Error: {e}")


@cli.command()
def list_jobs():

    print_header("ALL JOBS")
    
    if not check_server():
        print_error("API server is not running!")
        return
    
    try:
        response = requests.get(f"{API_BASE_URL}/jobs")
        
        if response.status_code != 200:
            print_error(f"Error: {response.status_code}")
            return
        
        data = response.json()
        
        if data['total'] == 0:
            print_info("No jobs found")
            return
        
        print(f"Total: {Colors.BOLD}{data['total']} jobs{Colors.END}\n")
        
        for job in data['jobs']:
            status_color = {
                'completed': Colors.GREEN,
                'processing': Colors.YELLOW,
                'failed': Colors.RED,
                'pending': Colors.BLUE
            }.get(job['status'], '')
            
            print(f"{status_color}{job['status']:12}{Colors.END} {job['job_id']:20} {job['filename']:30} {job['progress']:3}%")
        
    except Exception as e:
        print_error(f"Error: {e}")


@cli.command()
@click.argument('job_id')
def delete(job_id):

    print_header(f"DELETE JOB: {job_id}")
    
    if not check_server():
        print_error("API server is not running!")
        return
    
    # Confirm deletion
    if not click.confirm(f"Are you sure you want to delete job {job_id}?"):
        print_info("Cancelled")
        return
    
    try:
        response = requests.delete(f"{API_BASE_URL}/jobs/{job_id}")
        
        if response.status_code == 404:
            print_error("Job not found!")
            return
        
        if response.status_code != 200:
            print_error(f"Error: {response.status_code}")
            return
        
        result = response.json()
        print_success(result['message'])
        
    except Exception as e:
        print_error(f"Error: {e}")


@cli.command()
def health():

    print_header("API HEALTH CHECK")
    
    try:
        response = requests.get(f"{API_BASE_URL.replace('/api', '')}/health", timeout=5)
        
        if response.status_code != 200:
            print_error(f"Server unhealthy: {response.status_code}")
            return
        
        data = response.json()
        
        print_success(f"Status: {data['status']}")
        print(f"Version: {data['version']}")
        
        if 'services' in data:
            print("\nJobs:")
            for key, value in data['services'].items():
                print(f"  {key}: {value}")
        
    except requests.ConnectionError:
        print_error("Cannot connect to server!")
        print_info("Start the server with: uvicorn app.main:app --reload")
    except Exception as e:
        print_error(f"Error: {e}")


if __name__ == '__main__':
    cli()