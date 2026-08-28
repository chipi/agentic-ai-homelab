# fleetd — build/test/deploy surface (agents + operator; every target ends
# with an unambiguous PASS/FAIL line).
SHA     := $(shell git rev-parse --short HEAD)
LDFLAGS := -ldflags "-X main.version=$(SHA)"
MINI    := homelab
SSH     := ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes
DEST    := ~/fleetd

.PHONY: build vet smoke test deploy status stop start logs

build:
	@go build $(LDFLAGS) -o fleetd . && echo "BUILD PASS ($(SHA))" || (echo "BUILD FAIL"; exit 1)

vet:
	@go vet ./... && echo "VET PASS" || (echo "VET FAIL"; exit 1)

test:
	@go test ./... && echo "TEST PASS" || (echo "TEST FAIL"; exit 1)

smoke: build
	@./deploy/smoke.sh && echo "SMOKE PASS" || (echo "SMOKE FAIL"; exit 1)

# deploy: keep previous binary for 30-second rollback; bootstrap launchd.
# The mini is an INTEL Mac (x86_64) — cross-compile explicitly; the dev
# laptop is arm64 and a native build is "Bad CPU type" on the target.
deploy: vet
	@GOOS=darwin GOARCH=amd64 go build $(LDFLAGS) -o fleetd-amd64 . && echo "BUILD PASS amd64 ($(SHA))" || (echo "BUILD FAIL"; exit 1)
	@$(SSH) $(MINI) 'mkdir -p $(DEST) && [ -f $(DEST)/fleetd ] && cp $(DEST)/fleetd $(DEST)/fleetd.prev || true'
	@scp -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes deploy/fleetd.json deploy/com.homelab.fleetd.plist $(MINI):$(DEST)/
	@scp -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes fleetd-amd64 $(MINI):$(DEST)/fleetd
	@$(SSH) $(MINI) 'cp $(DEST)/com.homelab.fleetd.plist ~/Library/LaunchAgents/ && launchctl unload ~/Library/LaunchAgents/com.homelab.fleetd.plist 2>/dev/null; launchctl load ~/Library/LaunchAgents/com.homelab.fleetd.plist' \
		&& echo "DEPLOY PASS ($(SHA) → $(MINI))" || (echo "DEPLOY FAIL"; exit 1)

rollback:
	@$(SSH) $(MINI) 'cp $(DEST)/fleetd.prev $(DEST)/fleetd && launchctl unload ~/Library/LaunchAgents/com.homelab.fleetd.plist 2>/dev/null; launchctl load ~/Library/LaunchAgents/com.homelab.fleetd.plist' \
		&& echo "ROLLBACK PASS" || (echo "ROLLBACK FAIL"; exit 1)

status:
	@$(SSH) $(MINI) 'launchctl list | grep com.homelab.fleetd && tail -5 $(DEST)/fleetd.log' \
		&& echo "STATUS PASS" || (echo "STATUS FAIL (not loaded?)"; exit 1)

stop:
	@$(SSH) $(MINI) 'touch ~/signal-fleet/STOP ~/bugfix-fleet/STOP 2>/dev/null; launchctl unload ~/Library/LaunchAgents/com.homelab.fleetd.plist' \
		&& echo "STOP PASS (flags set + daemon unloaded)" || (echo "STOP FAIL"; exit 1)

start:
	@$(SSH) $(MINI) 'rm -f ~/signal-fleet/STOP ~/bugfix-fleet/STOP; launchctl load ~/Library/LaunchAgents/com.homelab.fleetd.plist' \
		&& echo "START PASS" || (echo "START FAIL"; exit 1)

logs:
	@$(SSH) $(MINI) 'tail -40 $(DEST)/fleetd.log'

chain: build
	@./fleetd chain -config deploy/chain.json $(if $(ISSUE),-issue $(ISSUE),) && echo "CHAIN PASS" || (echo "CHAIN FAIL"; exit 1)
