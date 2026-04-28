package com.github.juanfernandez.article;

import com.github.juanfernandez.article.repository.PreguntaRepository;
import com.github.juanfernandez.article.service.AiClientService;
import com.github.juanfernandez.article.service.PreguntaGeneratorService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

/**
 * Spring Boot auto-configuration for the optional Question Generator feature.
 *
 * <p>This configuration is completely independent of {@link ArticleGeneratorAutoConfiguration}
 * and is only activated when a {@link PreguntaRepository} bean is present in the application
 * context (which requires {@code spring-boot-starter-data-jpa} and a configured
 * {@code DataSource} in the consuming application).
 *
 * <p>Separating question generation into its own auto-configuration ensures that adding
 * JPA/PostgreSQL support for questions does not interfere with article generation in any way.
 *
 * <h2>Activation</h2>
 * <p>Add to your project:
 * <pre>
 * &lt;dependency&gt;
 *     &lt;groupId&gt;org.springframework.boot&lt;/groupId&gt;
 *     &lt;artifactId&gt;spring-boot-starter-data-jpa&lt;/artifactId&gt;
 * &lt;/dependency&gt;
 * </pre>
 * and define a {@code PreguntaRepository} bean (or let Spring Data JPA create it automatically
 * when the {@code Pregunta} entity is scanned).
 */
@AutoConfiguration(after = ArticleGeneratorAutoConfiguration.class)
public class PreguntaGeneratorAutoConfiguration {

    /**
     * Registers {@link PreguntaGeneratorService} when a {@link PreguntaRepository} bean is
     * present and no {@link PreguntaGeneratorService} bean has been defined by the application.
     *
     * @param aiClientService      shared AI client bean from {@link ArticleGeneratorAutoConfiguration}
     * @param preguntaRepository   Spring Data JPA repository for the {@code preguntas} table
     * @return fully configured {@link PreguntaGeneratorService}
     */
    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnBean(PreguntaRepository.class)
    public PreguntaGeneratorService preguntaGeneratorService(AiClientService aiClientService,
                                                              PreguntaRepository preguntaRepository) {
        return new PreguntaGeneratorService(aiClientService, preguntaRepository);
    }
}
