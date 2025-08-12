#!/usr/bin/env python3
"""
Test script for the batch build and publish system
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

def create_test_instance():
    """Create a minimal test instance"""
    return {
        "org": "test-org",
        "repo": "test-repo", 
        "number": 1,
        "state": "closed",
        "title": "Test PR",
        "body": "Test PR description",
        "base": {
            "label": "test-org:main",
            "ref": "main", 
            "sha": "test123"
        },
        "resolved_issues": [],
        "fix_patch": "# Test patch",
        "test_patch": "# Test patch",
        "instance_id": "test-org__test-repo-1"
    }

def test_dry_run():
    """Test dry run functionality"""
    print("🧪 Testing dry run functionality...")
    
    # Create temporary test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        test_instance = create_test_instance()
        f.write(json.dumps(test_instance) + '\n')
        temp_file = f.name
    
    try:
        # Test quick_publish.py dry run
        cmd = ['python', 'quick_publish.py', temp_file, '--dry-run', '--no-push']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ quick_publish.py dry run: PASSED")
        else:
            print(f"❌ quick_publish.py dry run: FAILED")
            print(f"Error: {result.stderr}")
            return False
        
        # Test batch_build_and_publish.py dry run
        cmd = ['python', 'batch_build_and_publish.py', 
               '--input', temp_file, 
               '--registry', 'test-registry',
               '--dry-run']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ batch_build_and_publish.py dry run: PASSED")
        else:
            print(f"❌ batch_build_and_publish.py dry run: FAILED")
            print(f"Error: {result.stderr}")
            return False
            
        return True
        
    finally:
        # Clean up
        Path(temp_file).unlink()

def test_help_commands():
    """Test help commands work"""
    print("🧪 Testing help commands...")
    
    scripts = ['quick_publish.py', 'batch_build_and_publish.py']
    
    for script in scripts:
        cmd = ['python', script, '--help']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and 'usage:' in result.stdout.lower():
            print(f"✅ {script} --help: PASSED")
        else:
            print(f"❌ {script} --help: FAILED")
            return False
    
    return True

def test_prerequisites():
    """Test prerequisite checking"""
    print("🧪 Testing prerequisites...")
    
    # Test Docker
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Docker: Available")
        else:
            print("❌ Docker: Not available")
            return False
    except FileNotFoundError:
        print("❌ Docker: Not found")
        return False
    
    # Test Multi-SWE-bench module
    try:
        import multi_swe_bench
        print("✅ Multi-SWE-bench: Available")
    except ImportError:
        print("❌ Multi-SWE-bench: Not available")
        return False
    
    return True

def test_jsonl_validation():
    """Test JSONL file validation"""
    print("🧪 Testing JSONL validation...")
    
    # Test valid JSONL
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        test_instance = create_test_instance()
        f.write(json.dumps(test_instance) + '\n')
        valid_file = f.name
    
    # Test invalid JSONL
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write('{"invalid": json}\n')  # Invalid JSON
        invalid_file = f.name
    
    try:
        # Test with valid file
        cmd = ['python', 'batch_build_and_publish.py', 
               '--input', valid_file,
               '--registry', 'test-registry',
               '--dry-run']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Valid JSONL: PASSED")
        else:
            print(f"❌ Valid JSONL: FAILED - {result.stderr}")
            return False
        
        # Test with invalid file
        cmd = ['python', 'batch_build_and_publish.py', 
               '--input', invalid_file,
               '--registry', 'test-registry', 
               '--dry-run']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("✅ Invalid JSONL rejection: PASSED")
        else:
            print("❌ Invalid JSONL rejection: FAILED (should have failed)")
            return False
            
        return True
        
    finally:
        # Clean up
        Path(valid_file).unlink()
        Path(invalid_file).unlink()

def main():
    """Run all tests"""
    print("🚀 Testing Multi-SWE-bench Batch Build and Publish System")
    print("=" * 60)
    
    tests = [
        ("Prerequisites", test_prerequisites),
        ("Help Commands", test_help_commands), 
        ("JSONL Validation", test_jsonl_validation),
        ("Dry Run", test_dry_run),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 Running {test_name} tests...")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: ALL PASSED")
            else:
                print(f"❌ {test_name}: SOME FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} test suites passed")
    
    if passed == total:
        print("🎉 All tests passed! System is ready to use.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())