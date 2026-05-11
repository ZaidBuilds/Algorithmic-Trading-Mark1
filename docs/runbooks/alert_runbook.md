# QuantumTrade Alert Runbook

This document describes each alert, its meaning, immediate actions, and escalation procedures.

---

## Critical Alerts

### BrokerDisconnected

**Severity:** Critical  
**Description:** The trading broker has been disconnected for more than 30 seconds.

**Immediate Actions:**
1. Check broker API status page (Alpaca/Binance status pages)
2. Verify API keys are valid and not expired
3. Check network connectivity
4. Review broker logs in `logs/trading_bot.log`

**Resolution Steps:**
1. If paper trading, restart the broker service
2. If live trading, switch to backup broker or paper trading mode
3. Verify connection with `GET /health/ready` endpoint
4. If persistent, pause trading until resolved

**Escalation:** After 5 minutes → PagerDuty or manual intervention required

---

### DailyLossLimitBreached

**Severity:** Critical  
**Description:** Daily P&L has dropped below -$2000 threshold.

**Immediate Actions:**
1. Stop all new trade signals immediately
2. Review open positions in dashboard
3. Consider manual position closure
4. Check for market anomalies or strategy issues

**Resolution Steps:**
1. Assess if losses are from legitimate market moves or errors
2. Close high-risk positions manually
3. Wait for market conditions to stabilize
4. Review and adjust strategy parameters
5. Reset daily P&L tracking after strategy review

**Escalation:** After 10 minutes → Manual review required

---

### DatabaseConnectionFailed

**Severity:** Critical  
**Description:** Cannot connect to the primary database.

**Immediate Actions:**
1. Check database container status: `docker ps`
2. Verify database logs: `docker logs qt-postgres`
3. Check connection string in environment variables
4. Verify network connectivity to database

**Resolution Steps:**
1. Restart database container if needed
2. If using SQLite, check file permissions in `data/` directory
3. Verify database credentials
4. Test connection with health endpoint

**Escalation:** After 5 minutes → Database administrator

---

### RedisDown

**Severity:** Critical  
**Description:** Cannot connect to Redis message bus.

**Immediate Actions:**
1. Check Redis container: `docker ps | grep redis`
2. Review Redis logs: `docker logs qt-redis`
3. Verify Redis is accepting connections

**Resolution Steps:**
1. Restart Redis container
2. Check for memory issues (Redis may have hit maxmemory)
3. Verify no firewall blocking port 6379
4. Consider clearing Redis data if corrupted

---

## Warning Alerts

### HighOrderLatency

**Severity:** Warning  
**Description:** 95th percentile order latency exceeds 1 second.

**Immediate Actions:**
1. Check broker API status and rate limits
2. Review network latency to broker
3. Check CPU/memory usage on trading server
4. Review pending orders in the system

**Resolution Steps:**
1. Reduce concurrent order volume if rate limited
2. Consider using a closer broker region
3. Optimize order placement logic
4. Monitor latency improves after adjustments

---

### PositionTrackingMismatch

**Severity:** Warning  
**Description:** Local portfolio value differs from broker by more than 1%.

**Immediate Actions:**
1. Compare positions locally vs broker
2. Check for recent fills not yet recorded
3. Verify no duplicate trades were sent

**Resolution Steps:**
1. Force sync positions from broker
2. Update local tracking database
3. Investigate root cause (race condition, missed update)
4. Add reconciliation logging

---

### HighMemoryUsage

**Severity:** Warning  
**Description:** System memory usage above 90%.

**Immediate Actions:**
1. Check running processes: `htop` or `docker stats`
2. Identify memory-intensive containers
3. Review recent log growth

**Resolution Steps:**
1. Restart high-memory containers if safe
2. Clear old log files if disk-bound
3. Add memory limit to containers
4. Consider increasing system memory

---

### LowDiskSpace

**Severity:** Warning  
**Description:** Available disk space below 10%.

**Immediate Actions:**
1. Check disk usage: `df -h`
2. Identify large directories: `du -sh */`
3. Check for old log files or data accumulation

**Resolution Steps:**
1. Clean up old log files (`logs/*.log`)
2. Remove old market data files
3. Archive historical data
4. Expand disk capacity if needed

---

## Alert Response Checklist

### For Critical Alerts:
- [ ] Acknowledge alert in monitoring system
- [ ] Assess impact on trading operations
- [ ] Execute immediate actions from runbook
- [ ] Communicate status to team
- [ ] Document resolution steps

### For Warning Alerts:
- [ ] Monitor for escalation to critical
- [ ] Plan fix during next maintenance window
- [ ] Check if similar alerts recur frequently
- [ ] Update runbook if new pattern emerges

---

## Contact Information

| Role | Contact | Response Time |
|------|---------|---------------|
| Primary On-Call | Telegram/Discord | 5 min |
| Secondary On-Call | Email/SMS | 15 min |
| Infrastructure | PagerDuty | 30 min |

---

## Related Documentation

- [Health Checks](../monitoring/health.md)
- [Deployment Guide](../deployment.md)
- [Troubleshooting Guide](../troubleshooting.md)