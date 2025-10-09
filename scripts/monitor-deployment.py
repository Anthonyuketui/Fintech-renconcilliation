#!/usr/bin/env python3
"""
Deployment monitoring and performance tracking for 30-minute cycles
"""

import time
import boto3
import json
from datetime import datetime, timedelta
import sys

class DeploymentMonitor:
    def __init__(self, environment='dev'):
        self.environment = environment
        self.ecs = boto3.client('ecs', region_name='us-east-1')
        self.logs = boto3.client('logs', region_name='us-east-1')
        self.cluster_name = f'fintech-reconciliation-{environment}'
        self.service_name = f'fintech-reconciliation-{environment}'
        
    def check_deployment_status(self):
        """Check current deployment status"""
        try:
            response = self.ecs.describe_services(
                cluster=self.cluster_name,
                services=[self.service_name]
            )
            
            if not response['services']:
                return {'status': 'NOT_FOUND', 'message': 'Service not found'}
            
            service = response['services'][0]
            
            return {
                'status': service['status'],
                'running_count': service['runningCount'],
                'desired_count': service['desiredCount'],
                'pending_count': service['pendingCount'],
                'deployment_status': service['deployments'][0]['status'] if service['deployments'] else 'UNKNOWN',
                'last_deployment': service['deployments'][0]['createdAt'] if service['deployments'] else None
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
    
    def get_recent_logs(self, minutes=10):
        """Get recent application logs"""
        try:
            log_group = f'/ecs/fintech-reconciliation-{self.environment}'
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=minutes)
            
            response = self.logs.filter_log_events(
                logGroupName=log_group,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                limit=50
            )
            
            return [event['message'] for event in response.get('events', [])]
        except Exception as e:
            return [f"Error fetching logs: {str(e)}"]
    
    def wait_for_deployment(self, timeout_minutes=15):
        """Wait for deployment to complete with progress tracking"""
        print(f"Monitoring deployment to {self.environment}...")
        start_time = time.time()
        timeout = timeout_minutes * 60
        
        while time.time() - start_time < timeout:
            status = self.check_deployment_status()
            
            if status['status'] == 'ACTIVE' and status['running_count'] == status['desired_count']:
                elapsed = (time.time() - start_time) / 60
                print(f"Deployment successful in {elapsed:.1f} minutes")
                return True
            
            print(f"Status: {status['deployment_status']}, Running: {status['running_count']}/{status['desired_count']}")
            time.sleep(30)
        
        print(f"Deployment timeout after {timeout_minutes} minutes")
        return False
    
    def performance_check(self):
        """Run performance checks on deployed service"""
        print("Running performance checks...")
        
        # Check service health
        status = self.check_deployment_status()
        if status['status'] != 'ACTIVE':
            print(f"Service not active: {status}")
            return False
        
        # Check recent logs for errors
        logs = self.get_recent_logs(5)
        error_count = sum(1 for log in logs if 'ERROR' in log or 'CRITICAL' in log)
        
        if error_count > 0:
            print(f"Found {error_count} errors in recent logs")
            for log in logs:
                if 'ERROR' in log or 'CRITICAL' in log:
                    print(f"  {log}")
        else:
            print("No errors in recent logs")
        
        print("Performance check completed")
        return True

def main():
    environment = sys.argv[1] if len(sys.argv) > 1 else 'dev'
    action = sys.argv[2] if len(sys.argv) > 2 else 'status'
    
    monitor = DeploymentMonitor(environment)
    
    if action == 'status':
        status = monitor.check_deployment_status()
        print(json.dumps(status, indent=2, default=str))
    
    elif action == 'wait':
        success = monitor.wait_for_deployment()
        sys.exit(0 if success else 1)
    
    elif action == 'check':
        success = monitor.performance_check()
        sys.exit(0 if success else 1)
    
    elif action == 'logs':
        logs = monitor.get_recent_logs(10)
        for log in logs[-10:]:  # Show last 10 logs
            print(log)
    
    else:
        print("Usage: python monitor-deployment.py <env> <action>")
        print("Actions: status, wait, check, logs")
        sys.exit(1)

if __name__ == '__main__':
    main()