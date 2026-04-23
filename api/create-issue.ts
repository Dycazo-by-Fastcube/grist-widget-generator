// api/create-issue.ts
// Vercel Serverless Function (Node.js) - Crée une issue GitHub

import type { VercelRequest, VercelResponse } from '@vercel/node';

interface Contact {
  name: string;
  email: string;
  jobTitle?: string;
}

interface RequestBody {
  nom_module: string;
  description: string;
  type_app: string;
  contact?: Contact;
}

export default async function handler(
  req: VercelRequest,
  res: VercelResponse
) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  // Handle preflight
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    // Parse request body (already parsed by Vercel)
    const { nom_module, description, type_app, contact } = req.body as RequestBody;

    // Validate
    if (!nom_module || !description || !type_app) {
      return res.status(400).json({ error: 'Missing required fields' });
    }

    // Get environment variables
    const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
    const GITHUB_OWNER = process.env.GITHUB_OWNER;
    const GITHUB_REPO = process.env.GITHUB_REPO || 'grist-widget-generator';
    const GRIST_API_URL = process.env.GRIST_API_URL;
    const GRIST_API_KEY = process.env.GRIST_API_KEY;
    const GRIST_DOC_ID  = process.env.GRIST_DOC_ID;
    const GRIST_TABLE_ID = process.env.GRIST_TABLE_ID || 'Demandes';

    if (!GITHUB_TOKEN || !GITHUB_OWNER) {
      console.error('Missing environment variables');
      return res.status(500).json({ error: 'Server configuration error' });
    }

    // Create issue via GitHub API
    const issueBody = `**Description :** ${description}

**Type :** ${type_app}`;

    const githubResponse = await fetch(
      `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/issues`,
      {
        method: 'POST',
        headers: {
          'Authorization': `token ${GITHUB_TOKEN}`,
          'Content-Type': 'application/json',
          'Accept': 'application/vnd.github.v3+json',
        },
        body: JSON.stringify({
          title: nom_module,
          body: issueBody,
          labels: ['widget-generation'],
        }),
      }
    );

    if (!githubResponse.ok) {
      const errorData = await githubResponse.json();
      console.error('GitHub API error:', errorData);
      return res.status(githubResponse.status).json({
        error: 'Failed to create issue',
        details: errorData.message,
      });
    }

    const issue = await githubResponse.json();

    // Store contact info in Grist (private, not visible on public GitHub)
    if (contact?.email && GRIST_API_URL && GRIST_API_KEY && GRIST_DOC_ID) {
      await fetch(
        `${GRIST_API_URL}/api/docs/${GRIST_DOC_ID}/tables/${GRIST_TABLE_ID}/records`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${GRIST_API_KEY}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            records: [{
              fields: {
                Nom:            contact.name,
                Email:          contact.email,
                Fonction:       contact.jobTitle || '',
                Widget_demande: nom_module,
                Issue_url:      issue.html_url,
                Date_demande:   new Date().toISOString(),
              },
            }],
          }),
        }
      ).catch(err => console.error('Failed to store contact in Grist:', err));
    }

    // Compute widget URLs (mirrors workflow slug logic)
    const slug = nom_module.toLowerCase().replace(/[^a-z0-9]/g, '_').substring(0, 40);
    const widget_url = `https://${GITHUB_OWNER}.github.io/${GITHUB_REPO}/widgets/${slug}/`;
    const grist_url = `${widget_url}widget.grist`;

    return res.status(200).json({
      success: true,
      issue_number: issue.number,
      issue_url: issue.html_url,
      widget_url,
      grist_url,
      message: 'Widget generation started! Check the issue for progress.',
    });

  } catch (error) {
    console.error('Error:', error);
    return res.status(500).json({
      error: 'Internal server error',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}
