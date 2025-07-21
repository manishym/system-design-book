---
name: Bug Report
about: Create a report to help us improve the consistent hashing system
title: '[BUG] '
labels: ['bug', 'needs-triage']
assignees: ''

---

## 🐛 Bug Description
A clear and concise description of what the bug is.

## 🔍 Steps to Reproduce
Steps to reproduce the behavior:
1. Deploy the system with '...'
2. Send request to '...'
3. Observe error '...'
4. See error

## ✅ Expected Behavior
A clear and concise description of what you expected to happen.

## 📸 Screenshots/Logs
If applicable, add screenshots or logs to help explain your problem.

```
[Paste relevant logs here]
```

## 🌍 Environment
**Deployment Environment:**
- Kubernetes Version: [e.g. v1.28.0]
- Platform: [e.g. K3s, Kind, EKS, GKE]
- Gateway Pods: [e.g. 3]
- KV Store Pods: [e.g. 6]

**Client Environment:**
- OS: [e.g. Ubuntu 22.04]
- Python Version: [e.g. 3.11]
- Library Versions: [e.g. requests 2.28.0]

## 🔧 Configuration
**Relevant configuration:**
```yaml
[Paste relevant configuration files]
```

## 📊 Impact
- [ ] System completely down
- [ ] Degraded performance
- [ ] Data loss/corruption
- [ ] Incorrect routing
- [ ] Other: ___________

## 🧪 Test Results
If you ran the test suite:
```bash
# Test command used
python run_tests.py --unit

# Test results
[Paste test output]
```

## 📋 Additional Context
Add any other context about the problem here.

## ✨ Possible Solution
If you have ideas on how to fix this bug, please describe them here. 