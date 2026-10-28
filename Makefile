.PHONY: up down demo inspect watch tools observe test lint chaos

up:        ## make up P=gcra          start one project (+ redis)
	docker compose --profile $(P) up --build -d

down:      ## stop everything
	docker compose --profile "*" down -v

demo:      ## make demo P=gcra        run that project's scripted scenarios with live output
	docker compose run --rm dev python -m tools.traffic --project $(P) --scenario all

inspect:   ## show rl:* keys, types, TTLs, values in Redis
	docker compose run --rm dev python -m tools.redis_inspect

watch:     ## raw Redis command stream (see Lua/INCR calls live)
	docker compose exec redis redis-cli monitor

tools:     ## RedisInsight on :5540
	docker compose --profile tools up -d redisinsight

observe:   ## Prometheus :9090 + Grafana :3000
	docker compose --profile observe up -d

test:      ## make test P=rate_limiters/algorithms/05_gcra
	docker compose run --rm dev pytest $(P)/tests -q

lint:
	docker compose run --rm dev sh -c "ruff check . && python -m tools.run_mypy"

chaos:     ## stop Redis mid-traffic and demonstrate fail-open/closed/fallback recovery
	bash rate_limiters/policies/04_failure_modes/scripts/chaos.sh
