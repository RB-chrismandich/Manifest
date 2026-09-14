import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

const STATUS = {
  extension: "ui-delivery-policy",
  status: "ready",
} as const;

export default function uiDeliveryPolicy(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "ui_delivery_status",
    label: "UI delivery status",
    description: "Report whether the Stitch UI delivery policy extension is loaded.",
    parameters: pi.zod.object({}).strict(),
    approval: "read",
    strict: true,
    async execute() {
      return {
        content: [{ type: "text", text: JSON.stringify(STATUS) }],
        details: STATUS,
      };
    },
  });
}
