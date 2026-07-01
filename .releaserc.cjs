module.exports = {
  branches: ["main"],
  plugins: [
    [
      "@semantic-release/commit-analyzer",
      {
        preset: "angular",
        releaseRules: [
          { type: "refactor", release: "patch" },
          { type: "audit", release: "patch" }
        ]
      }
    ],
    [
      "@semantic-release/release-notes-generator",
      {
        preset: "angular",
        writerOpts: {
          transform: (commit, context) => {
            let discard = true;
            const issues = [];
            const c = Object.assign({}, commit);
            
            if (c.type === 'feat') {
              c.type = 'Features';
              discard = false;
            } else if (c.type === 'fix') {
              c.type = 'Bug Fixes';
              discard = false;
            } else if (c.type === 'perf') {
              c.type = 'Performance Improvements';
              discard = false;
            } else if (c.type === 'revert' || c.revert) {
              c.type = 'Reverts';
              discard = false;
            } else if (c.type === 'refactor') {
              c.type = 'Code Refactoring';
              discard = false;
            } else if (c.type === 'audit') {
              c.type = 'Security Audits';
              discard = false;
            }

            if (discard) return undefined;

            if (c.scope === '*') {
              c.scope = '';
            }

            if (typeof c.hash === 'string') {
              c.shortHash = c.hash.substring(0, 7);
            }

            if (typeof c.subject === 'string') {
              let url = context.repository
                ? `${context.host}/${context.owner}/${context.repository}`
                : context.repoUrl;
              if (url) {
                url = `${url}/issues/`;
                c.subject = c.subject.replace(/#([0-9]+)/g, (_, issue) => {
                  issues.push(issue);
                  return `[#${issue}](${url}${issue})`;
                });
              }
              if (context.host) {
                c.subject = c.subject.replace(/\B@([a-z0-9](?:-?[a-z0-9/]){0,38})/g, (_, username) => {
                  if (username.includes('/')) {
                    return `@${username}`;
                  }
                  return `[@${username}](${context.host}/${username})`;
                });
              }
            }

            c.references = (c.references || []).filter(reference => {
              return issues.indexOf(reference.issue) === -1;
            });

            return c;
          }
        }
      }
    ],
    "@semantic-release/github"
  ]
};
