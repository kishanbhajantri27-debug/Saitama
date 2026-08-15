const nodemailer = require('nodemailer');

// With SMTP configured, mail goes out for real. Without it, messages are still
// composed and logged instead of delivered -- so the feature is visible during
// development, and a missing config never takes a request down with it.
const configured = Boolean(process.env.SMTP_HOST);

const transporter = configured
  ? nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port: Number(process.env.SMTP_PORT) || 587,
      secure: String(process.env.SMTP_SECURE) === 'true',
      auth: process.env.SMTP_USER
        ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS }
        : undefined
    })
  : nodemailer.createTransport({ jsonTransport: true });

if (!configured) {
  console.warn('[shop-crm] SMTP not configured — decision emails will be logged, not sent. See .env.example.');
}

function decisionEmail({ shopName, customerName, itemName, status }) {
  const approved = status === 'approved';
  const subject = approved
    ? `Your request for ${itemName} was approved`
    : `Update on your request for ${itemName}`;

  const body = approved
    ? `Hi ${customerName},\n\nGood news — your request for ${itemName} has been approved.\n\nGet in touch with us to arrange the next step.\n\n— ${shopName}`
    : `Hi ${customerName},\n\nThanks for your interest in ${itemName}. We are not able to fulfil this request right now.\n\nDo reach out if you would like to talk about alternatives.\n\n— ${shopName}`;

  return { subject, text: body };
}

// Never rejects: a mail failure must not turn a successful approval into an
// error for the shop owner. Problems are logged and swallowed.
async function sendDecision({ to, shopName, customerName, itemName, status }) {
  if (!to) return { sent: false, reason: 'no email on file' };

  const { subject, text } = decisionEmail({ shopName, customerName, itemName, status });
  const message = {
    from: process.env.SMTP_FROM || `${shopName} <no-reply@localhost>`,
    to,
    subject,
    text
  };

  try {
    const info = await transporter.sendMail(message);
    if (!configured) {
      console.log(`[shop-crm] would email ${to}: ${subject}`);
      return { sent: false, reason: 'smtp not configured', preview: info.message };
    }
    return { sent: true, id: info.messageId };
  } catch (err) {
    console.error(`[shop-crm] email to ${to} failed: ${err.message}`);
    return { sent: false, reason: err.message };
  }
}

module.exports = { sendDecision, decisionEmail, configured };
