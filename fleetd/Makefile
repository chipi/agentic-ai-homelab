# fleetd — build/test/deploy surface (agents + operator; every target ends
# with an unambiguous PASS/FAIL line).
SHA     := $(shell git rev-parse --short HEAD)
LDFLAGS := -ldflags "-X main.version=$(SHA)"
MINI    := homelab
SSH     := ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes
DEST    := ~/fleetd

.PHONY: build vet smoke test deploy rollback status stop start logs chain

build:
	@go build $(LDFLAGS) -o fleetd . && echo "BUILD PASS ($(SHA))" || (echo "BUILD FAIL"; exit 1)

vet:
	@go vet ./... && echo "VET PASS" || (echo "VET FAIL"; exit 1)

test:
	@go test ./... && echo "TEST PASS" || (echo "TEST FAIL"; exit 1)

smoke: build
	@./deploy/smoke.sh && echo "SMOKE PASS" || (echo "SMOKE FAIL"; exit 1)

# fleetd runs as the SYSTEM LaunchDaemon system/com.homelab.fleetd (since
# 567bd21) — never a LaunchAgent: a LaunchAgent copy would run a SECOND
# supervisor next to it. The plist is installed by infra/mini-setup.sh; these
# targets only swap the binary and restart the daemon.
LABEL   := system/com.homelab.fleetd
PLIST   := /Library/LaunchDaemons/com.homelab.fleetd.plist

# deploy: keep the previous binary for a 30-second rollback; swap atomically
# (mv, never overwrite a running binary in place); restart via kickstart.
# The live fleetd.json is NOT overwritten — a drift from deploy/fleetd.json is
# printed so the operator decides. The mini is an INTEL Mac (x86_64) —
# cross-compile explicitly; a native arm64 build is "Bad CPU type" there.
deploy: vet test
	@GOOS=darwin GOARCH=amd64 go build $(LDFLAGS) -o fleetd-amd64 . && echo "BUILD PASS amd64 ($(SHA))" || (echo "BUILD FAIL"; exit 1)
	@scp -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes fleetd-amd64 $(MINI):$(DEST)/fleetd.new
	@scp -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes deploy/fleetd.json $(MINI):$(DEST)/fleetd.json.repo
	@$(SSH) $(MINI) 'cd $(DEST) && python3 -c "import json,sys; a,b=(json.load(open(f)) for f in sys.argv[1:]); sys.exit(a!=b)" fleetd.json fleetd.json.repo \
		|| echo "!! live fleetd.json differs from the repo deploy/fleetd.json — not overwritten; review: diff $(DEST)/fleetd.json $(DEST)/fleetd.json.repo"'
	@$(SSH) $(MINI) 'cd $(DEST) && chmod +x fleetd.new && cp fleetd fleetd.prev && mv fleetd.new fleetd && sudo -n launchctl kickstart -k $(LABEL)' \
		&& echo "DEPLOY PASS ($(SHA) → $(MINI); previous binary kept as fleetd.prev)" || (echo "DEPLOY FAIL"; exit 1)

rollback:
	@$(SSH) $(MINI) 'cd $(DEST) && cp fleetd.prev fleetd.rollback && mv fleetd.rollback fleetd && sudo -n launchctl kickstart -k $(LABEL)' \
		&& echo "ROLLBACK PASS" || (echo "ROLLBACK FAIL"; exit 1)

status:
	@$(SSH) $(MINI) 'sudo -n launchctl print $(LABEL) | grep -E "^\s+(state|pid) =" && tail -5 $(DEST)/fleetd.log' \
		&& echo "STATUS PASS" || (echo "STATUS FAIL (not loaded?)"; exit 1)

# stop: STOP flags first (so a restart skips cycles), then bootout (KeepAlive
# would respawn a merely killed daemon). Flag paths match deploy/fleetd.json.
stop:
	@$(SSH) $(MINI) 'touch ~/signal-fleet/STOP ~/bugfix-fleet-STOP; sudo -n launchctl bootout $(LABEL)' \
		&& echo "STOP PASS (flags set + daemon booted out)" || (echo "STOP FAIL"; exit 1)

start:
	@$(SSH) $(MINI) 'rm -f ~/signal-fleet/STOP ~/bugfix-fleet-STOP; sudo -n launchctl bootstrap system $(PLIST)' \
		&& echo "START PASS" || (echo "START FAIL"; exit 1)

logs:
	@$(SSH) $(MINI) 'tail -40 $(DEST)/fleetd.log'

chain: build
	@./fleetd chain -config deploy/chain.json $(if $(ISSUE),-issue $(ISSUE),) && echo "CHAIN PASS" || (echo "CHAIN FAIL"; exit 1)
