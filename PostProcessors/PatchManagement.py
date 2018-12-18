#!/usr/bin/python
#
# Copyright 2018 Sebastien Tomasi
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from autopkglib import Processor, ProcessorError

import json
import requests
import os
import base64

__all__ = ["PatchManagement"]


class PatchManagement(Processor):
    description = ("Create a software tile and a patch policy scoped to a testing group and exclude a NOT MANAGED group. The templates are in the parent folder")
    input_variables = {
        "jss_importer_summary_result": {
            "required": True,
            "description": ("Description of interesting results.")
        },
        "patch_server": {
            "required": True,
            "description": ("Patch server where the definition exists")
        },
        "name_id":{
            "required": True,
            "description": ("Application name of the software")
        },
        "softwaretitleconfig_id":{
            "required": True,
            "description": ("Jamf software title settings ID")
        },
    }
    output_variables = {
    }



    __doc__ = description

    def jamf_requests(self, url, action, app_type, payload=None):
        b64Val = base64.b64encode("{0}:{1}".format(self.env["API_USERNAME"], self.env["API_PASSWORD"]))
        authorization = "Basic {0}".format(b64Val)
        if action == "POST":
            response = requests.request("GET", url, data="", headers={"Accept": "application/json", 'Authorization': authorization})
            resp_json = json.loads(response.text)
            if response.status_code == 200:
                action = "PUT"
            if "softwaretitleconfig" in url:
                if len(resp_json['patch policies']) == 0:
                    action = "POST"
                for entry in resp_json["patch policies"]:
                    patch_policy_name = "{0} - {1}".format(self.env.get("jss_importer_summary_result")["data"]["Name"],self.env.get("jss_importer_summary_result")["data"]["Version"])
                    if entry["name"] == patch_policy_name:
                        entry["id"]
                        url = "{0}/JSSResource/patchpolicies/id/{1}".format(self.env["JSS_URL"], entry["id"])
        response = requests.request(action, url, data=payload, headers={"Accept": "application/{0}".format(app_type), 'Authorization': authorization})
        print "***********************"
        print action, url
        print "status code:", response.status_code
        print "***********************"
        return response, action

    def find_file_in_override_postprocessors_path(self, path):
        override_path = ""
        repo_path = ""
        for entry in self.env["RECIPE_SEARCH_DIRS"]:
            if os.path.exists(os.path.join(entry,"PostProcessors",path)):
                repo_path = os.path.join(entry,"PostProcessors",path)
        for entry in self.env["RECIPE_OVERRIDE_DIRS"]:
            if os.path.exists(os.path.join(os.path.expanduser(entry),path)):
                override_path = os.path.join(os.path.expanduser(entry),path)
        if override_path:
            return override_path
        else:
            return repo_path

    def replace_text(self, text, replace_dict):  # pylint: disable=no-self-use
        """Substitute items in a text string.
        Args:
            text: A string with embedded %tags%.
            replace_dict: A dict, where
                key: Corresponds to the % delimited tag in text.
                value: Text to swap in.
        Returns:
            The text after replacement.
        """
        for key, value in replace_dict.iteritems():
            # Wrap our keys in % to match template tags.
            # print "{0}: {1}".format(key,value)
            text = text.replace("%%%s%%" % key, value)
        return text

    def get_obj_id(self,obj_type,obj_name):
        url = "{0}/JSSResource/{1}/name/{2}".format(self.env["JSS_URL"],obj_type,obj_name)
        # print url
        response, action = self.jamf_requests(url, "GET", "json")
        obj_data = json.loads(response.text)
        if obj_type is "packages":
            obj_id = obj_data["package"]["id"]
        elif obj_type is "categories":
            obj_id = obj_data["category"]["id"]
        return obj_id

    def update_softwaretitle(self,replace_dict, jamf_id):
        with open(self.find_file_in_override_postprocessors_path("SoftwareTitle.xml"), "r") as template_file:
            text = template_file.read()
        template = self.replace_text(text, replace_dict)
        url = "{0}/JSSResource/patchsoftwaretitles/id/{1}".format(self.env["JSS_URL"],str(jamf_id))
        response, action = self.jamf_requests(url, "POST", "xml", template)
        return response.status_code, action

    def create_patchpolicy(self, replace_dict):
        with open(self.find_file_in_override_postprocessors_path("PatchPolicy.xml"), "r") as template_file:
            text = template_file.read()
        template = self.replace_text(text, replace_dict)
        url = "{0}/JSSResource/patchpolicies/softwaretitleconfig/id/{1}".format(self.env["JSS_URL"],str(replace_dict["JAMF_ID"]))
        response, action = self.jamf_requests(url, "POST", "xml",template)
        return response.status_code, action

    def main(self):
        jss_importer_summary_result = self.env.get("jss_importer_summary_result")
        patch_server_name = self.env.get("patch_server")
        if patch_server_name == "Jamf":
            status = True
            url = "{0}/JSSResource/patchinternalsources/id/1".format(self.env["JSS_URL"])
            response, action = self.jamf_requests(url, "GET", "json")
            if response.status_code == 200:
                response = json.loads(response.text)["patch_internal_source"]
                if response["name"] == patch_server_name:
                    patch_server = response
        else:
            for server in range(1,11,1):
                url = "{0}/JSSResource/patchexternalsources/id/{1}".format(self.env["JSS_URL"],server)
                response, action = self.jamf_requests(url, "GET", "json")
                if response.status_code == 200:
                    response = json.loads(response.text)["patch_external_source"]
                    if response["name"] == patch_server_name:
                        patch_server = response

        name = jss_importer_summary_result["data"]["Name"]
        pkg_name = jss_importer_summary_result["data"]["Package"]
        name_id = self.env.get("name_id")
        jamf_id = self.env.get("softwaretitleconfig_id")
        version = jss_importer_summary_result["data"]["Version"]
        if patch_server_name != "Jamf":
            url = "https://{0}/patch/{1}".format(patch_server["host_name"], name_id)
            response = requests.request("GET", url)
            soft_def = json.loads(response.text)
            for patch in soft_def["patches"]:
                if patch["version"] == version:
                    status = True
        dict_software_title = {
            "NAME": name,
            "NAME_ID": name_id,
            "SOURCE": str(patch_server["id"]),
            "VERSION": version,
            "PACKAGE_ID": str(self.get_obj_id("packages", pkg_name)),
            "PACKAGE_NAME": pkg_name
        }
        dict_patch_policy = {
            "NAME": name,
            "JAMF_ID": jamf_id,
            "VERSION": version,
        }
        if status:
                softwaretitle, action = self.update_softwaretitle(dict_software_title, jamf_id)
                if softwaretitle == 201:
                    print "The software Title '{}' has been {}".format(name, action)
                    patchpolicy, action = self.create_patchpolicy(dict_patch_policy)
                    if patchpolicy == 201:
                        print "The patch policy '{} - {}' has been {}".format(name, version, action)


if __name__ == "__main__":
    processor = PatchManagement()
    processor.execute_shell()
