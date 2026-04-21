// api/create-issue.ts
// Vercel Edge Function - Crée une issue GitHub de manière sécurisée

export const config = {
  runtime: 'edge',
};

interface RequestBody {
  nom_module: string;
  description: string;
  type_app: string;
}

export default async function handler(req: Request) {
  // CORS headers
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json',
  };

  // Handle preflight
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers });
  }

  if (req.method !== 'POST') {
    return new Response(
      JSON.stringify({ error: 'Method not allowed' }),
      { status: 405, headers }
    );
  }

  try {
    // Parse request body
    const body: RequestBody = await req.json();
    const { nom_module, description, type_app } = body;

    // Validate
    if (!nom_module || !description || !type_app) {
      return new Response(
        JSON.stringify({ error: 'Missing required fields' }),
        { status: 400, headers }
      );
    }

    // Get environment variables
    const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
    const GITHUB_OWNER = process.env.GITHUB_OWNER;
    const GITHUB_REPO = process.env.GITHUB_REPO || 'grist-widget-generator';

    if (!GITHUB_TOKEN || !GITHUB_OWNER) {
      console.error('Missing environment variables');
      return new Response(
        JSON.stringify({ error: 'Server configuration error' }),
        { status: 500, headers }
      );
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
      return new Response(
        JSON.stringify({ 
          error: 'Failed to create issue',
          details: errorData.message 
        }),
        { status: githubResponse.status, headers }
      );
    }

    const issue = await githubResponse.json();

    // Success response
    return new Response(
      JSON.stringify({
        success: true,
        issue_number: issue.number,
        issue_url: issue.html_url,
        message: 'Widget generation started! Check the issue for progress.',
      }),
      { status: 200, headers }
    );

  } catch (error) {
    console.error('Error:', error);
    return new Response(
      JSON.stringify({ 
        error: 'Internal server error',
        message: error instanceof Error ? error.message : 'Unknown error'
      }),
      { status: 500, headers }
    );
  }
}
