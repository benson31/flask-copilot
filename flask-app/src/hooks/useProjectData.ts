import { Mutex } from 'async-mutex';
import { useState, useEffect, useRef } from 'react';
import { Project, Experiment } from '../types';
import { validate as isValidUUID, version as getUUIDVersion, v4 as uuidv4 } from 'uuid';

import { HTTP_SERVER } from '../config';
const STORAGE_KEY = 'flask_copilot_projects';
const MIGRATED_KEY = 'flask_copilot_projects_migrated';

// Types for interacting with the database
interface ExperimentResponse {
  id: string;
  projectId: string;
  name: string;
  createdAt: string;
  lastModified: string;
  data: any;
}

interface ProjectResponse {
  id: string;
  name: string;
  userId: string;
  createdAt: string;
  lastModified: string;
  experiments: ExperimentResponse[];
}

export interface ExperimentUpdate {
  id?: string;
  name?: string;
  isRunning?: boolean; // Track if experiment is currently computing
  [key: string]: any;
}

// This interface defines the contract for data sources (local storage, database, etc.)
interface ProjectDataSource {
  loadProjects: () => Promise<Project[]>;
  createProject: (name: string) => Promise<Project | null>;
  updateProject: (projectId: string, newName: string) => Promise<void>;
  deleteProject: (projectId: string) => Promise<void>;
  createExperiment: (projectId: string, name: string) => Promise<Experiment | null>;
  loadExperiment: (projectId: string, experimentId: string) => Promise<Experiment | null>;
  updateExperiment: (projectId: string, experiment: ExperimentUpdate) => Promise<void>;
  deleteExperiment: (projectId: string, experimentId: string) => Promise<void>;
  setExperimentRunning: (
    projectId: string,
    experimentId: string,
    isRunning: boolean
  ) => Promise<void>;
}

export interface ProjectData {
  projectsRef: React.RefObject<Project[]>;
  projects: Project[];
  loading: boolean;
  createProject: (name: string) => Promise<Project | null>;
  updateProject: (projectId: string, newName: string) => Promise<void>;
  deleteProject: (projectId: string) => Promise<void>;
  createExperiment: (projectId: string, name: string) => Promise<Experiment | null>;
  updateExperiment: (projectId: string, experiment: Experiment) => Promise<void>;
  deleteExperiment: (projectId: string, experimentId: string) => Promise<void>;
  setExperimentRunning: (
    projectId: string,
    experimentId: string,
    isRunning: boolean
  ) => Promise<void>;
  refreshProjects: () => Promise<void>;
}

// Just need to flatten fields from 'data'.
function flattenExperiments(serverExperiments: ExperimentResponse[]): Experiment[] {
  return serverExperiments.map(({ data, projectId, ...sqlFields }) => {
    // problemId does NOT come along for this ride.
    const experiment = {
      ...data,
      ...sqlFields,
    };
    return experiment;
  });
}

// Reformat from the ProjectResponseWithExperiments to the frontend Project.
function flattenProjects(serverProjects: ProjectResponse[]): Project[] {
  return serverProjects.map(({ userId, experiments, ...rest }: ProjectResponse) => {
    // userId does NOT come along for this ride.
    return {
      ...rest,
      experiments: flattenExperiments(experiments),
    };
  });
}

const httpServerUrl = HTTP_SERVER;
class ServerDataSource implements ProjectDataSource {
  private readonly mutex: Mutex = new Mutex();

  async migrateProjectsFromLocalStorage(): Promise<void> {
    const stored = localStorage.getItem(STORAGE_KEY);
    // Nothing to migrate
    if (!stored) {
      localStorage.setItem(MIGRATED_KEY, JSON.stringify(true));
      return;
    }

    try {
      const ls_projects = JSON.parse(stored);
      // Make sure everything has UUID ids but leave the rest of the data unchanged.
      const new_id_projects = ls_projects.map(({ id, ...rest }: Project) => {
        return {
          id: isValidUUID(id) && getUUIDVersion(id) == 4 ? id : uuidv4(),
          ...rest,
        };
      });
      // Reformat the project
      const send_projects = new_id_projects.map(({ id, name, experiments }: Project) => {
        return {
          id: id,
          name: name,
          experiments: experiments.map((exp: Experiment) => {
            return {
              data: exp,
            };
          }),
        };
      });
      const response = await fetch(`${httpServerUrl}/projects/migrate`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(send_projects),
      });
      if (!response.ok) {
        throw new Error(`migrateProjects response status: ${response.status}`);
      }

      // Update any changed IDs to match the backend.
      const results = await response.json();
      const id_map = results.new_ids;
      const final_id_projects = new_id_projects.map(({ id, ...rest }: Project) => {
        return {
          id: id in id_map ? id_map[id] : id,
          ...rest,
        };
      });

      // Everything is ok, reset the localStorage with new IDs up the localStorage.
      localStorage.setItem(STORAGE_KEY, JSON.stringify(final_id_projects));
      localStorage.setItem(MIGRATED_KEY, JSON.stringify(true));
    } catch (e) {
      console.error('Error migrating projects from localStorage:', e);
      return;
    }
  }

  async loadProjects(): Promise<Project[]> {
    try {
      // FIXME (trb): Perhaps there's a better spot to hook this is
      // in?? It will short-circuit, but ugh.
      await this.mutex.runExclusive(async () => {
        const migrateDone = localStorage.getItem(MIGRATED_KEY);
        if (!migrateDone) {
          await this.migrateProjectsFromLocalStorage();
        }
      });

      const response = await fetch(`${httpServerUrl}/projects/meta`);
      if (!response.ok) {
        throw new Error(`loadProjects response status: ${response.status}`);
      }
      return flattenProjects(await response.json());
    } catch (e) {
      console.error('Error loading projects from server:', e);
      return [];
    }
  }

  async createProject(name: string): Promise<Project | null> {
    try {
      const response = await fetch(`${httpServerUrl}/projects`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: name,
        }),
      });
      if (!response.ok) {
        throw new Error(`createProject response status: ${await response.text()}`);
      }
      const project = await response.json();
      return project;
    } catch (e) {
      console.error('Error creating project:', e);
      return null;
    }
  }

  async updateProject(projectId: string, newName: string): Promise<void> {
    try {
      // First we update the project metadata
      const response = await fetch(`${httpServerUrl}/projects/${projectId}`, {
        method: 'PUT',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: newName }),
      });
      if (!response.ok) {
        throw new Error(`updateProject response status: ${response.status}`);
      }
    } catch (e) {
      console.error('Error updating project:', e);
    }
  }

  async deleteProject(projectId: string): Promise<void> {
    try {
      const response = await fetch(`${httpServerUrl}/projects/${projectId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error(`deleteProject response status: ${response.status}`);
      }

      // Remove from LocalStorage
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const ls_projects = JSON.parse(stored);
        const projects = ls_projects.filter(({ id }: Project) => projectId != id);

        localStorage.setItem(STORAGE_KEY, JSON.stringify(projects));
      }
    } catch (e) {
      console.error('Error deleting project:', e);
    }
  }

  async createExperiment(projectId: string, name: string): Promise<Experiment | null> {
    try {
      const response = await fetch(`${httpServerUrl}/projects/${projectId}/experiments`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: name }),
      });
      if (!response.ok) {
        throw new Error(`createExperiment response status: ${response.status}`);
      }
      const result = await response.json();
      return result;
    } catch (e) {
      console.error('Error creating experiment:', e);
    }
    return null;
  }

  async loadExperiment(projectId: string, experimentId: string): Promise<Experiment | null> {
    try {
      const response = await fetch(
        `${httpServerUrl}/projects/${projectId}/experiments/${experimentId}`
      );
      if (!response.ok) {
        throw new Error(`createExperiment response status: ${response.status}`);
      }
      const result = await response.json();
      // Unpack the data from the response message
      const experiment = result.data;

      return experiment;
    } catch (e) {
      console.error('Error creating experiment:', e);
    }
    return null;
  }

  async updateExperiment(projectId: string, experiment: ExperimentUpdate): Promise<void> {
    try {
      const response = await fetch(
        `${httpServerUrl}/projects/${projectId}/experiments/${experiment.id}`,
        {
          method: 'PUT',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ data: experiment }),
        }
      );
      if (!response.ok) {
        throw new Error(`updateExperiment response status: ${response.status}`);
      }
    } catch (e) {
      console.error('Error updating experiment:', e);
    }
  }

  async deleteExperiment(projectId: string, experimentId: string): Promise<void> {
    try {
      const response = await fetch(
        `${httpServerUrl}/projects/${projectId}/experiments/${experimentId}`,
        {
          method: 'DELETE',
        }
      );
      if (!response.ok) {
        throw new Error(`deleteExperiment response status: ${response.status}`);
      }
    } catch (e) {
      console.error('Error deleting experiment:', e);
    }
  }

  async setExperimentRunning(
    projectId: string,
    experimentId: string,
    isRunning: boolean
  ): Promise<void> {
    await this.updateExperiment(projectId, { id: experimentId, isRunning: isRunning });
  }
}

// TODO: Future server implementation
// class ServerDataSource implements ProjectDataSource {
//   async loadProjects(): Promise<Project[]> {
//     const response = await fetch('/api/projects');
//     return response.json();
//   }
//   // ...
// }

// Hook for managing project data
export const useProjectData = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  const projectsRef = useRef(projects);
  useEffect(() => {
    projectsRef.current = projects;
  }, [projects]);

  // TODO(later): Swap this to use ServerDataSource
  const dataSource: ProjectDataSource = new ServerDataSource();

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    setLoading(true);
    try {
      const data = await dataSource.loadProjects();
      setProjects(data);
      projectsRef.current = data;
    } catch (error) {
      console.error('Error loading projects:', error);
    } finally {
      setLoading(false);
    }
  };

  const createProject = async (name: string): Promise<Project | null> => {
    const newProject = await dataSource.createProject(name);
    await loadProjects();
    return newProject;
  };

  const updateProject = async (projectId: string, newName: string): Promise<void> => {
    await dataSource.updateProject(projectId, newName);
    await loadProjects();
  };

  const deleteProject = async (projectId: string): Promise<void> => {
    await dataSource.deleteProject(projectId);
    await loadProjects();
  };

  const createExperiment = async (projectId: string, name: string): Promise<Experiment | null> => {
    const newExperiment = await dataSource.createExperiment(projectId, name);
    await loadProjects();
    return newExperiment;
  };

  const loadExperiment = async (
    projectId: string,
    experimentId: string
  ): Promise<Experiment | null> => {
    const experiment = await dataSource.loadExperiment(projectId, experimentId);
    return experiment;
  };
  const updateExperiment = async (projectId: string, experiment: Experiment) => {
    await dataSource.updateExperiment(projectId, experiment);
    await loadProjects();
  };

  const deleteExperiment = async (projectId: string, experimentId: string) => {
    await dataSource.deleteExperiment(projectId, experimentId);
    await loadProjects();
  };

  const setExperimentRunning = async (
    projectId: string,
    experimentId: string,
    isRunning: boolean
  ) => {
    await dataSource.setExperimentRunning(projectId, experimentId, isRunning);
    await loadProjects();
  };

  return {
    projectsRef,
    projects,
    loading,
    createProject,
    updateProject,
    deleteProject,
    createExperiment,
    loadExperiment,
    updateExperiment,
    deleteExperiment,
    setExperimentRunning,
    refreshProjects: loadProjects,
  };
};
