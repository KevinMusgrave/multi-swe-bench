#!/usr/bin/env python3
"""
Test Results Comparison Script

Compares test results between two dataset files for specified instance numbers.
Shows which tests are in both files and which are unique to each file.

Usage:
    python compare_test_results.py file1.jsonl file2.jsonl --instances 3609 3615 3617
    python compare_test_results.py file1.jsonl file2.jsonl --instances all
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple
from collections import defaultdict

class TestResultsComparator:
    def __init__(self, file1_path: str, file2_path: str):
        self.file1_path = Path(file1_path)
        self.file2_path = Path(file2_path)
        self.file1_data = {}
        self.file2_data = {}
        
    def load_datasets(self):
        """Load both dataset files into memory"""
        print(f"Loading {self.file1_path}...")
        with open(self.file1_path, 'r') as f:
            for line in f:
                instance = json.loads(line.strip())
                self.file1_data[instance['number']] = instance
        
        print(f"Loading {self.file2_path}...")
        with open(self.file2_path, 'r') as f:
            for line in f:
                instance = json.loads(line.strip())
                self.file2_data[instance['number']] = instance
        
        print(f"File 1: {len(self.file1_data)} instances")
        print(f"File 2: {len(self.file2_data)} instances")
    
    def get_test_sets(self, instance: Dict[str, Any]) -> Dict[str, Set[str]]:
        """Extract all test sets from an instance"""
        test_sets = {}
        
        # Extract from test result objects
        for result_type in ['run_result', 'test_patch_result', 'fix_patch_result']:
            if result_type in instance:
                result = instance[result_type]
                test_sets[f'{result_type}_passed'] = set(result.get('passed_tests', []))
                test_sets[f'{result_type}_failed'] = set(result.get('failed_tests', []))
                test_sets[f'{result_type}_skipped'] = set(result.get('skipped_tests', []))
        
        # Extract from transition categories
        for transition_type in ['n2p_tests', 's2p_tests', 'f2p_tests', 'p2p_tests']:
            if transition_type in instance:
                test_sets[transition_type] = set(instance[transition_type])
        
        # Extract from fixed_tests (keys only)
        if 'fixed_tests' in instance:
            test_sets['fixed_tests'] = set(instance['fixed_tests'].keys())
        
        # Extract from failed_tests and skipped_tests lists
        if 'failed_tests' in instance:
            test_sets['failed_tests'] = set(instance['failed_tests'])
        if 'skipped_tests' in instance:
            test_sets['skipped_tests'] = set(instance['skipped_tests'])
        
        return test_sets
    
    def compare_instance(self, instance_number: int) -> Dict[str, Any]:
        """Compare test results for a specific instance number"""
        if instance_number not in self.file1_data:
            return {'error': f'Instance {instance_number} not found in file 1'}
        if instance_number not in self.file2_data:
            return {'error': f'Instance {instance_number} not found in file 2'}
        
        instance1 = self.file1_data[instance_number]
        instance2 = self.file2_data[instance_number]
        
        tests1 = self.get_test_sets(instance1)
        tests2 = self.get_test_sets(instance2)
        
        # Get all test set types that exist in either file
        all_test_types = set(tests1.keys()) | set(tests2.keys())
        
        comparison = {
            'instance_number': instance_number,
            'title1': instance1.get('title', 'N/A')[:80] + '...' if len(instance1.get('title', '')) > 80 else instance1.get('title', 'N/A'),
            'title2': instance2.get('title', 'N/A')[:80] + '...' if len(instance2.get('title', '')) > 80 else instance2.get('title', 'N/A'),
            'test_sets': {}
        }
        
        for test_type in sorted(all_test_types):
            set1 = tests1.get(test_type, set())
            set2 = tests2.get(test_type, set())
            
            comparison['test_sets'][test_type] = {
                'file1_count': len(set1),
                'file2_count': len(set2),
                'common': sorted(set1 & set2),
                'only_in_file1': sorted(set1 - set2),
                'only_in_file2': sorted(set2 - set1),
                'common_count': len(set1 & set2),
                'only_file1_count': len(set1 - set2),
                'only_file2_count': len(set2 - set1)
            }
        
        return comparison
    
    def print_comparison_summary(self, comparison: Dict[str, Any]):
        """Print a summary of the comparison results"""
        if 'error' in comparison:
            print(f"❌ {comparison['error']}")
            return
        
        instance_num = comparison['instance_number']
        print(f"\n{'='*80}")
        print(f"INSTANCE #{instance_num}")
        print(f"{'='*80}")
        print(f"File 1: {comparison['title1']}")
        print(f"File 2: {comparison['title2']}")
        print()
        
        # Summary table
        print(f"{'Test Set':<25} {'File1':<8} {'File2':<8} {'Common':<8} {'Only F1':<8} {'Only F2':<8}")
        print("-" * 80)
        
        for test_type, data in comparison['test_sets'].items():
            if data['file1_count'] > 0 or data['file2_count'] > 0:  # Only show non-empty sets
                print(f"{test_type:<25} {data['file1_count']:<8} {data['file2_count']:<8} "
                      f"{data['common_count']:<8} {data['only_file1_count']:<8} {data['only_file2_count']:<8}")
    
    def print_detailed_comparison(self, comparison: Dict[str, Any], show_test_names: bool = False):
        """Print detailed comparison results"""
        if 'error' in comparison:
            return
        
        for test_type, data in comparison['test_sets'].items():
            if data['file1_count'] == 0 and data['file2_count'] == 0:
                continue
                
            print(f"\n--- {test_type.upper()} ---")
            
            if data['common_count'] > 0:
                print(f"✓ Common tests: {data['common_count']}")
                if show_test_names and data['common']:
                    for test in data['common'][:5]:  # Show first 5
                        print(f"    {test}")
                    if len(data['common']) > 5:
                        print(f"    ... and {len(data['common']) - 5} more")
            
            if data['only_file1_count'] > 0:
                print(f"📁 Only in File 1: {data['only_file1_count']}")
                if show_test_names and data['only_in_file1']:
                    for test in data['only_in_file1'][:5]:  # Show first 5
                        print(f"    {test}")
                    if len(data['only_in_file1']) > 5:
                        print(f"    ... and {len(data['only_in_file1']) - 5} more")
            
            if data['only_file2_count'] > 0:
                print(f"📂 Only in File 2: {data['only_file2_count']}")
                if show_test_names and data['only_in_file2']:
                    for test in data['only_in_file2'][:5]:  # Show first 5
                        print(f"    {test}")
                    if len(data['only_in_file2']) > 5:
                        print(f"    ... and {len(data['only_in_file2']) - 5} more")
    
    def compare_instances(self, instance_numbers: List[int], detailed: bool = False, show_test_names: bool = False):
        """Compare multiple instances and print results"""
        for instance_num in instance_numbers:
            comparison = self.compare_instance(instance_num)
            self.print_comparison_summary(comparison)
            
            if detailed:
                self.print_detailed_comparison(comparison, show_test_names)
    
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
    parser.add_argument('--detailed', action='store_true', help='Show detailed comparison for each test set')
    parser.add_argument('--show-test-names', action='store_true', help='Show actual test names (implies --detailed)')
    parser.add_argument('--list-instances', action='store_true', help='List available instances in both files')
    
    args = parser.parse_args()
    
    # Validate files exist
    if not Path(args.file1).exists():
        print(f"Error: File {args.file1} does not exist")
        return 1
    if not Path(args.file2).exists():
        print(f"Error: File {args.file2} does not exist")
        return 1
    
    # Create comparator and load data
    comparator = TestResultsComparator(args.file1, args.file2)
    comparator.load_datasets()
    
    # List instances if requested
    if args.list_instances:
        file1_instances, file2_instances, common_instances = comparator.get_available_instances()
        print(f"\nFile 1 instances: {sorted(file1_instances)}")
        print(f"File 2 instances: {sorted(file2_instances)}")
        print(f"Common instances: {sorted(common_instances)}")
        return 0
    
    # Determine which instances to compare
    if not args.instances:
        print("Error: Please specify --instances or --list-instances")
        return 1
    
    if args.instances == ['all']:
        _, _, common_instances = comparator.get_available_instances()
        instance_numbers = sorted(common_instances)
        print(f"Comparing all {len(instance_numbers)} common instances")
    else:
        try:
            instance_numbers = [int(x) for x in args.instances]
        except ValueError:
            print("Error: Instance numbers must be integers or 'all'")
            return 1
    
    # Perform comparison
    detailed = args.detailed or args.show_test_names
    comparator.compare_instances(instance_numbers, detailed, args.show_test_names)
    
    return 0

if __name__ == '__main__':
    exit(main())