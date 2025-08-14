#!/usr/bin/env python3
"""
Test Results Comparison Script

Compares test results between two dataset files for specified instance numbers.
Shows which tests are in both files and which are unique to each file.
Outputs results in JSON format for LLM-friendly processing.

Usage:
    python compare_test_results.py file1.jsonl file2.jsonl --instances 3609 3615 3617
    python compare_test_results.py file1.jsonl file2.jsonl --instances all
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple
from collections import defaultdict

class TestResultsComparator:
    def __init__(self, file1_path: str, file2_path: str):
        self.file1_path = Path(file1_path)
        self.file2_path = Path(file2_path)
        self.file1_data = {}
        self.file2_data = {}
        
    def load_datasets(self, quiet=False):
        """Load both dataset files into memory"""
        if not quiet:
            print(f"Loading {self.file1_path}...", file=sys.stderr)
        with open(self.file1_path, 'r') as f:
            for line in f:
                instance = json.loads(line.strip())
                self.file1_data[instance['number']] = instance
        
        if not quiet:
            print(f"Loading {self.file2_path}...", file=sys.stderr)
        with open(self.file2_path, 'r') as f:
            for line in f:
                instance = json.loads(line.strip())
                self.file2_data[instance['number']] = instance
        
        if not quiet:
            print(f"File 1: {len(self.file1_data)} instances", file=sys.stderr)
            print(f"File 2: {len(self.file2_data)} instances", file=sys.stderr)
    
    def get_all_test_fields(self, instance: Dict[str, Any]) -> Dict[str, Set[str]]:
        """Extract all possible test-related fields from an instance"""
        test_fields = {}
        
        # Direct test transition fields (can be dict or list)
        for field_name in ['f2p_tests', 'n2p_tests', 's2p_tests', 'p2p_tests', 'fixed_tests']:
            if field_name in instance:
                field_data = instance[field_name]
                if isinstance(field_data, dict):
                    test_fields[field_name] = set(field_data.keys())
                elif isinstance(field_data, list):
                    test_fields[field_name] = set(field_data)
                else:
                    test_fields[field_name] = set()
            else:
                test_fields[field_name] = set()
        
        # Test result fields from result objects
        for result_type in ['run_result', 'test_patch_result', 'fix_patch_result']:
            if result_type in instance:
                result = instance[result_type]
                for test_status in ['passed_tests', 'failed_tests', 'skipped_tests']:
                    field_name = f'{result_type}_{test_status}'
                    test_fields[field_name] = set(result.get(test_status, []))
            else:
                # Add empty sets for missing result types
                for test_status in ['passed_tests', 'failed_tests', 'skipped_tests']:
                    field_name = f'{result_type}_{test_status}'
                    test_fields[field_name] = set()
        
        # Legacy direct test fields (if they exist)
        for field_name in ['failed_tests', 'skipped_tests']:
            if field_name in instance:
                field_data = instance[field_name]
                if isinstance(field_data, list):
                    test_fields[field_name] = set(field_data)
                elif isinstance(field_data, dict):
                    test_fields[field_name] = set(field_data.keys())
                else:
                    test_fields[field_name] = set()
            else:
                test_fields[field_name] = set()
        
        return test_fields
    
    def compare_instance(self, instance_number: int) -> Dict[str, Any]:
        """Compare test results for a specific instance number"""
        if instance_number not in self.file1_data:
            return {'error': f'Instance {instance_number} not found in file 1'}
        if instance_number not in self.file2_data:
            return {'error': f'Instance {instance_number} not found in file 2'}
        
        instance1 = self.file1_data[instance_number]
        instance2 = self.file2_data[instance_number]
        
        tests1 = self.get_all_test_fields(instance1)
        tests2 = self.get_all_test_fields(instance2)
        
        # Get all test field types that exist in either file
        all_test_types = set(tests1.keys()) | set(tests2.keys())
        
        comparison = {
            'instance_number': instance_number,
            'title1': instance1.get('title', 'N/A'),
            'title2': instance2.get('title', 'N/A'),
            'test_fields': {}
        }
        
        for test_type in sorted(all_test_types):
            set1 = tests1.get(test_type, set())
            set2 = tests2.get(test_type, set())
            
            comparison['test_fields'][test_type] = {
                'file1_count': len(set1),
                'file2_count': len(set2),
                'common_count': len(set1 & set2),
                'only_file1_count': len(set1 - set2),
                'only_file2_count': len(set2 - set1),
                'match': len(set1) == len(set2) and len(set1 - set2) == 0 and len(set2 - set1) == 0,
                'common_tests': sorted(list(set1 & set2)),
                'only_in_file1': sorted(list(set1 - set2)),
                'only_in_file2': sorted(list(set2 - set1))
            }
        
        return comparison
    
    def compare_instances(self, instance_numbers: List[int]) -> List[Dict[str, Any]]:
        """Compare multiple instances and return results as list"""
        results = []
        for instance_num in instance_numbers:
            comparison = self.compare_instance(instance_num)
            results.append(comparison)
        return results
    
    def get_available_instances(self) -> Tuple[Set[int], Set[int], Set[int]]:
        """Get available instance numbers in both files"""
        file1_instances = set(self.file1_data.keys())
        file2_instances = set(self.file2_data.keys())
        common_instances = file1_instances & file2_instances
        
        return file1_instances, file2_instances, common_instances

def main():
    parser = argparse.ArgumentParser(description='Compare test results between two dataset files')
    parser.add_argument('file1', help='First dataset file (JSONL format)')
    parser.add_argument('file2', help='Second dataset file (JSONL format)')
    parser.add_argument('--instances', nargs='+', help='Instance numbers to compare (or "all" for all common instances)')
    parser.add_argument('--list-instances', action='store_true', help='List available instances in both files')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')
    
    args = parser.parse_args()
    
    # Validate files exist
    if not Path(args.file1).exists():
        print(f"Error: File {args.file1} does not exist", file=sys.stderr)
        return 1
    if not Path(args.file2).exists():
        print(f"Error: File {args.file2} does not exist", file=sys.stderr)
        return 1
    
    # Create comparator and load data
    comparator = TestResultsComparator(args.file1, args.file2)
    comparator.load_datasets(quiet=True)  # Always quiet for JSON output
    
    # List instances if requested
    if args.list_instances:
        file1_instances, file2_instances, common_instances = comparator.get_available_instances()
        result = {
            'file1_instances': sorted(list(file1_instances)),
            'file2_instances': sorted(list(file2_instances)),
            'common_instances': sorted(list(common_instances))
        }
        print(json.dumps(result, indent=2 if args.pretty else None))
        return 0
    
    # Determine which instances to compare
    if not args.instances:
        print("Error: Please specify --instances or --list-instances", file=sys.stderr)
        return 1
    
    if args.instances == ['all']:
        _, _, common_instances = comparator.get_available_instances()
        instance_numbers = sorted(common_instances)
    else:
        try:
            instance_numbers = [int(x) for x in args.instances]
        except ValueError:
            print("Error: Instance numbers must be integers or 'all'", file=sys.stderr)
            return 1
    
    # Perform comparison and output JSON
    results = comparator.compare_instances(instance_numbers)
    print(json.dumps(results, indent=2 if args.pretty else None))
    
    return 0

if __name__ == '__main__':
    exit(main())