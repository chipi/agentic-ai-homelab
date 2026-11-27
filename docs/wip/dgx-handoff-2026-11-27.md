# DGX handoff, 2026-11-27: M2c to M2bw, then prod by 23:20Z

Two one-shot checks were scheduled in a homelab session that is about to be closed. Session crons die with
it, so this note is their source. A new homelab session recreates them (CronCreate, one-shot) or runs them
by hand at these times.

The operator's instructions, 2026-11-27:

- "give space to robotics lab all day long to run plans": the DGX stays in robotics mode through the day.
- The standing rule: prod by 23:20Z.

Times are UTC. The X3's clock is UTC+1, so cron expressions written there are local times.

## 1. 17:27Z (18:27 local, cron `27 18 27 11 *`): M2c end, then start M2bw

On dgx-llm-1 (`ssh -o BatchMode=yes markodragoljevic@dgx-llm-1`):

1. **Check that M2c has finished.**
    - `robotics-train` has exited: `sudo -n docker inspect -f '{{.State.Status}}' robotics-train`.
    - The run `/opt/robotics/microduck-nav/logs/rsl_rl/microduck_nav_deploy/2026-11-27_08-08-02`
      reached 1500 iterations (the last save and the log's last lines).
    - If it is still training, read the ETA and check again after it. Start nothing while it trains.
2. **Copy the run.** Copy that folder to `/work/microduck-nav-runs/m2c/`, as for M2a and M2b. Check
   that the file count and size match, then message robotics lab with the path.
3. **Start M2bw** (M2b plus walls, 400 iterations; robotics lab's spec, operator's go):
    - Prepare: `sudo -n -u ops /home/ops/agentic-ai-homelab/infra/robotics/microduck/prepare.sh microduck-nav 32ac389`
      (the full SHA if it asks), and confirm HEAD is 32ac389.
    - As ops, back up `.env` to `.env.m2c`, then write `.env`:

      ```text
      # microduck-nav M2bw, M2b plus walls, 400 iterations (robotics-lab; operator go 2026-11-27)
      ROBOTICS_PROJECT=microduck-nav
      ROBOTICS_TASK=Mjlab-Nav-Deploy-Room-MicroDuck
      ROBOTICS_NUM_ENVS=4096
      ROBOTICS_TRAIN_ARGS=--agent.max-iterations 400 --agent.save-interval 50
      ROBOTICS_MAX_RUNTIME=180m
      MICRODUCK_WALKER_ONNX=/cache/assets/walker-seed-v10/velstand.onnx
      ```

      The walker ONNX's sha256 starts `ce894d30` (checked 10:25Z).
    - Then run `~/bin/gpu-mode-swap.sh robotics --json`. After M2c ends, the mode is free.
4. **Watch the first iterations.**
    - At iteration 10, report the iteration time to robotics lab. Above 26 s a run of 400 does not fit
      180 min; say so.
    - At the first resets, check the room line: every reset has a room, with no "no room" count.
    - At the cap (start + 180 min + 5 min), copy the run to `/work/microduck-nav-runs/m2bw/` and message
      robotics lab.

## 2. 22:37Z (23:37 local, cron `37 23 27 11 *`): swap the DGX to prod

1. Confirm that M2c's folder was copied to `/work/microduck-nav-runs/m2c/`, and that nothing is still
   running in `robotics-train`.
2. If a robotics run is still going, do not swap: tell the operator and robotics lab.
3. Otherwise run `~/bin/gpu-mode-swap.sh prod --json` on dgx-llm-1.
4. Check that both vLLMs answer, on :8003 and :8005.
5. Message robotics lab that the DGX is in prod.

Delete this note once both are done.
