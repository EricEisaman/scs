"""
Authority management per BGS-MP-SYNC §4.7 and §4.8
- itemOwners: {instanceId -> {ownerClientId, lastUpdatedAt}}
- envArrivalOrder: {envName -> [client_id]} FIFO
- envAuthority: {envName -> client_id} = head of arrival list
"""
import time
from typing import Dict, List, Optional, Set

class AuthorityManager:
    def __init__(self):
        self.itemOwners: Dict[str, Dict] = {}  # instanceId -> {ownerClientId, lastUpdatedAt}
        self.envArrivalOrder: Dict[str, List[str]] = {}  # envName -> [client_id]
        self.envAuthority: Dict[str, str] = {}  # envName -> client_id
        self.clientEnvs: Dict[str, str] = {}  # client_id -> envName

    def client_arrives(self, client_id: str, env_name: str):
        self.clientEnvs[client_id] = env_name
        if env_name not in self.envArrivalOrder:
            self.envArrivalOrder[env_name] = []
        if client_id not in self.envArrivalOrder[env_name]:
            self.envArrivalOrder[env_name].append(client_id)

        # If env was empty, this client becomes authority
        if env_name not in self.envAuthority:
            self.envAuthority[env_name] = client_id
            return {"became_authority": True, "previous": None, "new": client_id, "reason": "arrival"}
        return {"became_authority": False}

    def client_leaves(self, client_id: str):
        env_name = self.clientEnvs.pop(client_id, None)
        if not env_name:
            return []

        events = []

        # Remove from arrival order
        if env_name in self.envArrivalOrder:
            if client_id in self.envArrivalOrder[env_name]:
                self.envArrivalOrder[env_name].remove(client_id)

        # If was env authority, promote next
        if self.envAuthority.get(env_name) == client_id:
            if self.envArrivalOrder.get(env_name):
                new_auth = self.envArrivalOrder[env_name][0]
                self.envAuthority[env_name] = new_auth
                events.append({
                    "type": "env-authority-changed",
                    "environmentName": env_name,
                    "previousAuthorityId": client_id,
                    "newAuthorityId": new_auth,
                    "reason": "failover"
                })
            else:
                del self.envAuthority[env_name]
                events.append({
                    "type": "env-authority-changed",
                    "environmentName": env_name,
                    "previousAuthorityId": client_id,
                    "newAuthorityId": None,
                    "reason": "disconnect"
                })

        # Release all explicit claims owned by this client
        to_release = [iid for iid, data in self.itemOwners.items() if data["ownerClientId"] == client_id]
        for iid in to_release:
            del self.itemOwners[iid]
            events.append({
                "type": "item-authority-changed",
                "instanceId": iid,
                "previousOwnerId": client_id,
                "newOwnerId": None,
                "reason": "disconnect"
            })

        return events

    def claim(self, instanceId: str, client_id: str, now: Optional[int] = None, idle_timeout_ms: int = 10000):
        now = now or int(time.time()*1000)
        existing = self.itemOwners.get(instanceId)

        if not existing:
            self.itemOwners[instanceId] = {"ownerClientId": client_id, "lastUpdatedAt": now}
            return {"accepted": True, "previous": None, "new": client_id, "reason": "claim"}

        if existing["ownerClientId"] == client_id:
            existing["lastUpdatedAt"] = now
            return {"accepted": True, "previous": client_id, "new": client_id, "reason": "refresh", "already_owned": True}

        # Check idle timeout
        if now - existing["lastUpdatedAt"] >= idle_timeout_ms:
            prev = existing["ownerClientId"]
            self.itemOwners[instanceId] = {"ownerClientId": client_id, "lastUpdatedAt": now}
            return {"accepted": True, "previous": prev, "new": client_id, "reason": "claim", "idle": True}

        return {"accepted": False, "currentOwnerId": existing["ownerClientId"]}

    def release(self, instanceId: str, client_id: str):
        existing = self.itemOwners.get(instanceId)
        if not existing or existing["ownerClientId"] != client_id:
            return {"released": False}
        del self.itemOwners[instanceId]
        return {"released": True, "previous": client_id, "new": None, "reason": "release"}

    def refresh(self, instanceId: str, client_id: str):
        existing = self.itemOwners.get(instanceId)
        if existing and existing["ownerClientId"] == client_id:
            existing["lastUpdatedAt"] = int(time.time()*1000)

    def get_resolved_owner(self, instanceId: str, env_name: str) -> Optional[str]:
        # Tier 1: explicit owner
        if instanceId in self.itemOwners:
            return self.itemOwners[instanceId]["ownerClientId"]
        # Tier 2: env authority
        return self.envAuthority.get(env_name)

    def get_env_authority(self, env_name: str) -> Optional[str]:
        return self.envAuthority.get(env_name)