# -*- coding: utf-8 -*-
# Copyright: (c) 2024, Red Hat
#
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


OUTBOUND_RELATION_KEY = "outbound_relations"
INBOUND_RELATION_KEY = "inbound_relations"
OUTBOUND_RELATION = "outbound"
INBOUND_RELATION = "inbound"


class CmdbRelation(object):
    """
    CmdbRelation is a representation of the relation from CMDB Instance API.
    Please refer to: https://developer.servicenow.com/dev.do#!/reference/api/utah/rest/cmdb-instance-api#cmdb-POST-instance-relation
    """

    def __init__(self, value):
        if "sys_id" not in value:
            raise ValueError("Relation has no sys_id")
        if "type" not in value or not isinstance(value["type"], dict):
            raise ValueError("Relation has no type or type is not a dictionary")
        if "target" not in value or not isinstance(value["type"], dict):
            raise ValueError("Relation has no target or target is not a dictionary")

        self.sys_id = value["sys_id"]
        self.type_name = value["type"]["display_value"]
        self.type_id = value["type"]["value"]
        self.target_id = value["target"]["value"]
        self.target_name = value["target"]["display_value"]

    def __eq__(self, o):
        # new relations don't have a sys_id yet
        if o.sys_id and self.sys_id:
            return o.sys_id == self.sys_id
        return o.target_id == self.target_id and o.type_id == self.type_id

    def to_payload(self):
        return dict(
            type=self.type_id,
            target=self.target_id,
        )

    def to_json(self):
        return dict(
            sys_id=self.sys_id,
            target=dict(value=self.target_id, display_value=self.target_name),
            type=dict(value=self.type_id, display_value=self.type_name),
        )

    @classmethod
    def from_values(cls, type_sys_id, target_sys_id):
        d = dict(
            sys_id=None,
            type=dict(value=type_sys_id, display_value=""),
            target=dict(value=target_sys_id, display_value=""),
        )
        return cls(d)


class CmdbItemRelations(object):
    """CmdbItemRelations manage the relations of a configuration item."""

    def __init__(self, configuration_item=None):
        self.relations = []
        # holds the tainted(added/deleted) relations as a tuple (direction, action, relation)
        self.tainted = []

        if configuration_item:
            self.configuration_item = configuration_item
            self.__read(configuration_item)

    def __iter__(self):
        for dir, relation in self.relations:
            yield dir, relation

    def clone(self):
        c = CmdbItemRelations()
        c.relations = self.relations[:]
        return c

    def get(self, direction, target_id):
        """Get returns a relation based on direction and target_id"""
        for dir, relation in self:
            if relation.target_id == target_id and dir == direction:
                return relation
        return None

    def add(self, direction, relation):
        """Add adds a new relation.
        User must call update to actually make the request.
        """
        for dir, action, r in self.tainted:
            if dir == direction and r == relation and action == "add":
                return
        self.tainted.append((direction, "add", relation))

    def remove(self, direction, relation):
        """Remove removes a relation.
        User must call update to actually make the request.
        """
        for dir, action, r in self.tainted:
            if dir == direction and r == relation and action == "remove":
                return
        self.tainted.append((direction, "remove", relation))

    def update(self, api_path, generic_client):
        """
        Update updates the configuration item with the tainted relations.
        Returns True if relations changed or False otherwise.
        """
        if len(self.tainted) == 0:
            return

        payload = self.__create_payload()
        if payload:
            result = generic_client.create_record(
                api_path, payload, check_mode=False, query=None
            )
            # return a new instance of the ci
            return CmdbItemRelations(result)

        # remove relations by calling DELETE endpoint
        # SNow does not returned any response following a succesfull DELETE op
        # So, we just remove the relation from a clone and return it.
        clone = self.clone()
        for dir, action, rel in self.tainted:
            if action == "add":
                continue
            generic_client.delete_record_by_sys_id(api_path, rel.sys_id)
            for idx, r in enumerate(clone):
                if r[1].sys_id == rel.sys_id:
                    clone.relations.pop(idx)
                    break
        return clone

    def to_json(self):
        result = dict(outbound_relations=[], inbound_relations=[])
        for dir, rel in self:
            if dir == OUTBOUND_RELATION:
                result["outbound_relations"].append(rel.to_json())
            if dir == INBOUND_RELATION:
                result["inbound_relations"].append(rel.to_json())
        return result

    def __create_payload(self):
        """
        Create payload for added relations
        Return: True,payload if there're relation to be added. False, dict() otherwise
        """
        payload = dict(
            source="ServiceNow",
        )
        has = False
        for dir, action, rel in self.tainted:
            if action == "remove":
                continue
            has = True
            if dir == OUTBOUND_RELATION:
                if "outbound_relations" not in payload:
                    payload["outbound_relations"] = []
                payload["outbound_relations"].append(rel.to_payload())
            elif dir == INBOUND_RELATION:
                payload["inbound_relations"].append(rel.to_payload())
        return payload if has else None

    def __read(self, configuration_item):
        for r in configuration_item[OUTBOUND_RELATION_KEY]:
            self.relations.append((OUTBOUND_RELATION, CmdbRelation(r)))
        for r in configuration_item[INBOUND_RELATION_KEY]:
            self.relations.append((INBOUND_RELATION, CmdbRelation(r)))
