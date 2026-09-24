# CHANGE THESE PARTS:
def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=60
    #... your existing init...
    app.last_send_ms = 0
    app.mp_client = None

    if HAS_MP:
        base_url = "https://scs-207.onrender.com"
        try:
            if 'localhost' in window.location.hostname:
                base_url = "http://localhost:10000"
        except: pass

        app.mp_client = MultiplayerClient(
            base_url=base_url,
            environment_name="level1", # NOT environment=
            character_name="Player"
        )
        async def join_mp():
            res = await app.mp_client.join()
            app.client_id = res.get("client_id")
        aio.run(join_mp())

def onKeyHold(app, keys):
    app.keys_held=set(keys)
    for pid, p in app.world.players.items():
        move_x=0
        if p.keys["left"] in app.keys_held: move_x-=1
        if p.keys["right"] in app.keys_held: move_x+=1
        jump=p.keys["jump"] in app.keys_held
        app.world.apply_input(pid, move_x, jump)
    # REMOVE the send from here!

def onStep(app):
    # 1. Pull signals - Datastar best practice: read-only in step
    if HAS_MP:
        try:
            sig = get_signal("character-state-update")
            if sig and isinstance(sig, dict):
                for u in sig.get("updates", []):
                    cid=u.get("clientId")
                    if cid and cid!=app.client_id:
                        app.remote_players[cid]=u
            app.datastar_connected=is_datastar_connected()
        except Exception as e:
            print(e)

    app.world.step()

    # 2. Throttled send - 20Hz max, not 60Hz, and NOT in onKeyHold
    if app.mp_client and app.client_id and "local_0" in app.world.players:
        now = int(window.Date.now())
        if now - app.last_send_ms > 50: # 50ms = 20Hz per spec
            app.last_send_ms = now
            lp=app.world.players["local_0"]
            async def send():
                await app.mp_client.send_character_state(
                    position=[lp.x, lp.y],
                    velocity=[lp.vx, lp.vy],
                    animationState=lp.state,
                    onGround=lp.on_ground
                )
            aio.run(send())

    # camera...