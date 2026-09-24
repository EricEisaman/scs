"""
Dirty filter per BGS §5.2.1 + freshness matrix per §5.2.2
"""
from typing import Dict, List
import math

class DirtyFilter:
    def __init__(self, pos_epsilon=0.005, rot_dot_threshold=0.99996):
        self.cache: Dict[str, Dict] = {}
        self.pos_epsilon = pos_epsilon
        self.rot_dot_threshold = rot_dot_threshold

    def is_dirty(self, instanceId: str, new_state: Dict) -> bool:
        cached = self.cache.get(instanceId)
        if not cached:
            self.cache[instanceId] = new_state.copy()
            return True

        # pos check
        new_pos = new_state.get("pos", [0,0])
        old_pos = cached.get("pos", [0,0])
        if len(new_pos) != len(old_pos):
            dirty = True
        else:
            dirty = any(abs(a-b) > self.pos_epsilon for a,b in zip(new_pos, old_pos))

        if not dirty:
            # rot check (dot product)
            new_rot = new_state.get("rot", [0,0,0,1])
            old_rot = cached.get("rot", [0,0,0,1])
            dot = sum(a*b for a,b in zip(new_rot, old_rot))
            if abs(dot) < self.rot_dot_threshold:
                dirty = True

        if not dirty:
            # categorical
            for k in ["isCollected", "collectedByClientId", "ownerClientId"]:
                if new_state.get(k) != cached.get(k):
                    dirty = True
                    break

        if dirty:
            self.cache[instanceId] = new_state.copy()
        return dirty

class FreshnessMatrix:
    def __init__(self):
        # freshness[env][instanceId][clientId] = fresh|stale
        self.matrix: Dict[str, Dict[str, Dict[str, bool]]] = {}

    def ensure_env(self, env: str):
        if env not in self.matrix:
            self.matrix[env] = {}

    def client_enters(self, env: str, client_id: str, all_instance_ids: List[str]):
        self.ensure_env(env)
        for iid in all_instance_ids:
            if iid not in self.matrix[env]:
                self.matrix[env][iid] = {}
            self.matrix[env][iid][client_id] = False  # stale -> needs bootstrap

    def client_leaves(self, env: str, client_id: str):
        if env not in self.matrix:
            return
        for iid in list(self.matrix[env].keys()):
            self.matrix[env][iid].pop(client_id, None)

    def mark_dirty(self, env: str, instanceId: str, owner_id: str, all_clients_in_env: List[str]):
        self.ensure_env(env)
        if instanceId not in self.matrix[env]:
            self.matrix[env][instanceId] = {}
        # Owner stays fresh, others become stale
        for cid in all_clients_in_env:
            if cid == owner_id:
                self.matrix[env][instanceId][cid] = True
            else:
                self.matrix[env][instanceId][cid] = False

    def get_stale_clients(self, env: str, instanceId: str) -> List[str]:
        if env not in self.matrix or instanceId not in self.matrix[env]:
            return []
        return [cid for cid, fresh in self.matrix[env][instanceId].items() if not fresh]

    def mark_fresh(self, env: str, instanceId: str, client_id: str):
        if env in self.matrix and instanceId in self.matrix[env]:
            self.matrix[env][instanceId][client_id] = True

    def pin_owner(self, env: str, instanceId: str, owner_id: str):
        self.ensure_env(env)
        if instanceId not in self.matrix[env]:
            self.matrix[env][instanceId] = {}
        self.matrix[env][instanceId][owner_id] = True