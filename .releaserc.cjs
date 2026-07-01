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
            
            if (commit.type === 'feat') {
              commit.type = 'Features';
              discard = false;
            } else if (commit.type === 'fix') {
              commit.type = 'Bug Fixes';
              discard = false;
            } else if (commit.type === 'perf') {
              commit.type = 'Performance Improvements';
              discard = false;
            } else if (commit.type === 'revert' || commit.revert) {
              commit.type = 'Reverts';
              discard = false;
            } else if (commit.type === 'refactor') {
              commit.type = 'Code Refactoring';
              discard = false;
            } else if (commit.type === 'audit') {
              commit.type = 'Security Audits';
              discard = false;
            }

            if (discard) return undefined;

            if (commit.scope === '*') {
              commit.scope = '';
            }

            if (typeof commit.hash === 'string') {
              commit.shortHash = commit.hash.substring(0, 7);
            }

            if (typeof commit.subject === 'string') {
              let url = context.repository
                ? `${context.host}/${context.owner}/${context.repository}`
                : context.repoUrl;
              if (url) {
                url = `${url}/issues/`;
                commit.subject = commit.subject.replace(/#([0-9]+)/g, (_, issue) => {
                  issues.push(issue);
                  return `[#${issue}](${url}${issue})`;
                });
              }
              if (context.host) {
                commit.subject = commit.subject.replace(/\B@([a-z0-9](?:-?[a-z0-9/]){0,38})/g, (_, username) => {
                  if (username.includes('/')) {
                    return `@${username}`;
                  }
                  return `[@${username}](${context.host}/${username})`;
                });
              }
            }

            commit.references = commit.references.filter(reference => {
              return issues.indexOf(reference.issue) === -1;
            });

            return commit;
          }
        }
      }
    ],
    "@semantic-release/github"
  ]
};
