## Pull Request Checklist

### Description
<!-- Provide a brief description of the changes in this PR -->

### Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Test improvements
- [ ] Performance improvement
- [ ] Refactoring

### Testing

#### Unit Tests
- [ ] I have added unit tests for new functionality
- [ ] All existing unit tests pass locally
- [ ] Test coverage is maintained above 70%
- [ ] I have run `./test-ci-locally.sh` successfully

#### Integration Tests
- [ ] Integration tests pass with the changes
- [ ] I have tested the changes manually

#### Test Commands Run
```bash
# Check these commands work in your environment
go test -v -cover .                                      # Basic unit test run
go test -v -race -coverprofile=coverage.out .           # Full unit test with race detection
./test/test-ci-locally.sh                               # Complete CI simulation
./test/integration/run-integration-tests.sh --quick     # Integration tests
./test/chaos/chaos-test.sh --quick                      # Chaos testing
```

### Rate Limiter Specific

#### Multi-User Functionality
- [ ] Changes maintain user isolation
- [ ] User auto-creation works correctly
- [ ] Custom user limits are respected
- [ ] Redis keys follow the established patterns

#### Algorithm Support
- [ ] Changes work with both Token Bucket and Leaky Bucket
- [ ] Lua scripts are properly updated if modified
- [ ] Performance characteristics are maintained

### Code Quality
- [ ] My code follows the Go style guidelines
- [ ] I have performed a self-review of my code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation

### Dependencies
- [ ] I have not introduced unnecessary dependencies
- [ ] Any new dependencies are justified and documented

### Performance
- [ ] Changes do not negatively impact rate limiting performance
- [ ] Redis operations remain atomic where required
- [ ] Response times are within acceptable limits (< 10ms p99)

---

**Note**: All PRs must pass the automated test suite before merging. The CI pipeline will:
1. Run unit tests with coverage validation (≥70% required)
2. Execute integration tests in a Kubernetes environment
3. Validate multi-user functionality and Redis integration

If tests fail, please review the output and update your changes accordingly. 