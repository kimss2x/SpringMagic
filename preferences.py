import bpy

class SpringMagicPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    update_url: bpy.props.StringProperty(
        name="Update URL",
        description="URL to a JSON {\"version\": \"1.2.3\"} or plain version string",
        default=""
    )
    last_update_status: bpy.props.StringProperty(
        name="Last Update Status",
        default="",
        options={'HIDDEN'}
    )
    last_update_version: bpy.props.StringProperty(
        name="Last Update Version",
        default="",
        options={'HIDDEN'}
    )
    last_checked: bpy.props.StringProperty(
        name="Last Checked",
        default="",
        options={'HIDDEN'}
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "update_url")
        if self.last_update_status:
            layout.label(text=self.last_update_status)
        if self.last_checked:
            layout.label(text=f"Last checked: {self.last_checked}")
