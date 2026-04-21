// api/create-issue.ts
// Vercel Serverless Function (Node.js) - Crée une issue GitHub

import type { VercelRequest, VercelResponse } from '@vercel/node';

interface RequestBody {
  nom_module: string;
  description: string;
  type_app: string;
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
    const { nom_module, description, type_app } = req.body as RequestBody;

    // Validate
    if (!nom_module || !description || !type_app) {
      return res.status(400).json({ error: 'Missing required fields' });
    }

    // Get environment variables
    const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
    const GITHUB_OWNER = process.env.GITHUB_OWNER;
    const GITHUB_REPO = process.env.GITHUB_REPO || 'grist-widget-generator';

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

    // Success response
    return res.status(200).json({
      success: true,
      issue_number: issue.number,
      issue_url: issue.html_url,
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
